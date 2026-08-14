import argparse
from ultralytics import YOLO


def parse_args():
    parser = argparse.ArgumentParser(description='Run validation on a YOLO dataset.')
    parser.add_argument('--weights', default='best.pt', help='Weights file to validate')
    parser.add_argument('--data', default='data.yaml', help='Dataset config file')
    parser.add_argument('--batch', type=int, default=16, help='Batch size for validation')
    parser.add_argument('--imgsz', type=int, default=640, help='Image size for validation')
    parser.add_argument('--device', default='0', help='Device to use for validation (0 or cpu)')
    return parser.parse_args()


def main():
    args = parse_args()
    model = YOLO(args.weights)
    results = model.val(
        data=args.data,
        batch=args.batch,
        imgsz=args.imgsz,
        device=args.device,
    )
    print(results)


if __name__ == '__main__':
    main()
