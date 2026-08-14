import argparse
from ultralytics import YOLO


def parse_args():
    parser = argparse.ArgumentParser(description='Run inference on a folder or file using a YOLO model.')
    parser.add_argument('--weights', default='best.pt', help='Weights file to use for inference')
    parser.add_argument('--source', default='test_images', help='Image folder or video file to run inference on')
    parser.add_argument('--imgsz', type=int, default=640, help='Inference image size')
    parser.add_argument('--conf', type=float, default=0.25, help='Confidence threshold')
    parser.add_argument('--device', default='0', help='Device to run inference on (0 or cpu)')
    parser.add_argument('--save', action='store_true', help='Save inference results')
    parser.add_argument('--save_dir', default='runs/detect', help='Directory to save inference results')
    return parser.parse_args()


def main():
    args = parse_args()
    model = YOLO(args.weights)
    model.predict(
        source=args.source,
        imgsz=args.imgsz,
        conf=args.conf,
        device=args.device,
        save=args.save,
        save_dir=args.save_dir,
    )


if __name__ == '__main__':
    main()
