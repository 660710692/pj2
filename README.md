# Water Hyacinth YOLOv11n Training

This project uses Ultralytics YOLO and your labeled dataset to fine-tune a YOLOv11n model.

## Files created
- `data.yaml` - dataset configuration for YOLO
- `train.py` - training helper script

## Data layout
- `data/images/train/`
- `data/images/val/`
- `data/labels/train/`
- `data/labels/val/`

Every image must have a matching label file in the same split.

## Train using your existing model
Use the current `best.pt` weights to continue training:

```bash
source venv/bin/activate
python train.py --weights best.pt --epochs 50 --batch 16
```

## If you want to start from a clean YOLOv11n base
If you have `yolov11n.pt`, replace the weights argument:

```bash
python train.py --weights yolov11n.pt --epochs 50 --batch 16
```

## Check results
Training output will be saved in `runs/train/waterhyacinth-v11n`.

## Inference after training
Run inference on `test_images/` and save results:

```bash
source venv/bin/activate
python infer.py --weights runs/train/waterhyacinth-v11n/weights/best.pt --source test_images --save
```

## Validate the model
Run validation using your dataset split:

```bash
source venv/bin/activate
python validate.py --weights runs/train/waterhyacinth-v11n/weights/best.pt
```

## Notes
- Keep using YOLOv11n-style models; your existing `best.pt` is already YOLOv11n-compatible.
- The most important improvement is good labeled data and a proper validation split.
- If training is slow, use a smaller batch size or `device=cpu` only if necessary.
