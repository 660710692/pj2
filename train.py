import argparse
from ultralytics import YOLO


def parse_args():
    parser = argparse.ArgumentParser(description='Train a YOLOv11n model on water hyacinth data.')
    parser.add_argument('--weights', default='best.pt', help='Base weights file, e.g. best.pt or yolov11n.pt')
    parser.add_argument('--data', default='data.yaml', help='Dataset config file')
    parser.add_argument('--epochs', type=int, default=50, help='Number of training epochs')
    parser.add_argument('--imgsz', type=int, default=640, help='Image size for training')
    parser.add_argument('--batch', type=int, default=16, help='Batch size')
    parser.add_argument('--patience', type=int, default=30, help='Early stopping patience')
    parser.add_argument('--project', default='runs/train', help='Project directory for training results')
    parser.add_argument('--name', default='waterhyacinth-v11n', help='Training run name')
    parser.add_argument('--device', default='0', help='Device, e.g. 0 or cpu')
    return parser.parse_args()


def main():
    args = parse_args()
    model = YOLO(args.weights)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        project=args.project,
        name=args.name,
        device=args.device,
        exist_ok=True,
    )


if __name__ == '__main__':
    main()
