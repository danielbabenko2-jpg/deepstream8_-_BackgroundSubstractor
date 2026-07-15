from pathlib import Path
import datetime
import os
import cv2
import ctypes
import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst
import pyds
import cupy as cp
import numpy as np

import config
from parser import parse_args
args = parse_args()

frame_cnt = 0
bg_subtractor = cv2.createBackgroundSubtractorMOG2(
    history=500,
    varThreshold=36,
    detectShadows=False
)


Path(config.output_dir).mkdir(parents=True, exist_ok=True)

def save_video(frames, counter):
    """Сохраняет список кадров в видео файл"""
    if not frames:
        return
    
    # Получаем размеры кадра
    height, width = frames[0].shape[:2]
    
    # Создаем имя файла с временной меткой
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(config.output_dir, f"output_video_{timestamp}_{counter}.mp4")
    
    # Создаем VideoWriter
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, 30.0, (width, height))
    
    if not out.isOpened():
        print(f"Не удалось создать VideoWriter для {output_path}")
        return
    
    # Записываем все кадры
    for frame in frames:
        out.write(frame)
    
    out.release()
    print(f"Видео сохранено: {output_path} (кадров: {len(frames)})")
    
    # Очищаем список кадров
    frames.clear()

def pgie_src_pad_buffer_probe(pad, info, u_data):
    global frame_cnt, video_counter, video_frames
    
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return Gst.PadProbeReturn.OK

    # Retrieve batch metadata from the gst_buffer
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    
    while l_frame is not None:
        frame_cnt += 1
        
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break
        
        frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        frame_index = frame_meta.batch_id
        
        # Получаем данные кадра с GPU
        data_type, shape, strides, dataptr, size = pyds.get_nvds_buf_surface_gpu(hash(gst_buffer), frame_index)
        ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
        ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
        c_data_ptr = ctypes.pythonapi.PyCapsule_GetPointer(dataptr, None)
        unownedmem = cp.cuda.UnownedMemory(c_data_ptr, size, owner=None) 
        memptr = cp.cuda.MemoryPointer(unownedmem, 0)

        # Создание массива CuPy (все еще на GPU)
        n_frame_gpu = cp.ndarray(shape=shape, dtype=data_type, memptr=memptr, strides=strides, order='C')
        n_frame_cpu = cp.asnumpy(n_frame_gpu)
        
        # Конвертируем BGR в RGB для корректной обработки
        n_frame_rgb = cv2.cvtColor(n_frame_cpu, cv2.COLOR_BGR2RGB)
        
        # Применяем background subtractor
        fg_mask = bg_subtractor.apply(n_frame_rgb)
        
        # Морфологическая обработка маски для удаления шума
        kernel = np.ones((5, 5), np.uint8)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        
        # Находим контуры движущихся объектов
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # СОЗДАЕМ ЧЕРНО-БЕЛОЕ ИЗОБРАЖЕНИЕ (как в первом коде)
        # Преобразуем маску в 3-канальное изображение (черно-белое)
        frame_with_boxes = cv2.cvtColor(fg_mask, cv2.COLOR_GRAY2BGR)
        
        # Рисуем зеленые рамки вокруг объектов
        min_area = 500
        objects_count = 0
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > min_area:
                x, y, w, h = cv2.boundingRect(contour)
                cv2.rectangle(frame_with_boxes, (x, y), (x + w, y + h), (0, 255, 0), 2)  # Зеленые рамки
                cv2.putText(frame_with_boxes, f'Obj {int(area)}', 
                           (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.5, (0, 255, 0), 2)
                objects_count += 1
        
        # Добавляем информацию на кадр
        cv2.putText(frame_with_boxes, f'Frame: {frame_cnt}', 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(frame_with_boxes, f'Objects: {objects_count}', 
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        # Добавляем информацию о временной метке, если доступна
        if args.rtsp_ts:
            ts = frame_meta.ntp_timestamp/1000000000
            time_str = datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            cv2.putText(frame_with_boxes, f'Time: {time_str}', 
                       (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        # Сохраняем кадр для видео (каждые 500 кадров)
        config.video_frames.append(frame_with_boxes)
        
        # Если набралось 500 кадров, сохраняем видео
        if len(config.video_frames) >= config.VIDEO_FRAMES_LIMIT:
            config.video_counter += 1
            save_video(config.video_frames, config.video_counter)
        
        frame_number = frame_meta.frame_num
        print(f"Frame Number={frame_number}, Objects={objects_count}")

        try:
            l_frame = l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK