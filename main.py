from parser import parse_args
from pipeline import run_pipeline

if __name__ == "__main__":
    args = parse_args()
    run_pipeline(args)