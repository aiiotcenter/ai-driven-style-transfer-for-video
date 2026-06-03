# StarryNight

An application to train, experiment with, and deploy real-time style transfer models

# Demo
![ezgif com-gif-maker](https://user-images.githubusercontent.com/15766192/141136055-0bd08f88-2445-421a-bcfc-05680daa4730.gif)

# Installation

1. Install Python 3.9 and Node 16 or 18
2. Install python dependencies using `pip install -r requirements.txt`
3. cd into `frontend` and run `npm install`

# Usage

1. cd into `backend` and run `python manage.py runserver`
2. cd into `frontend` and run `npm start`

# Evaluation

Use the evaluator at `backend/scripts/evaluate_style_transfer.py` to benchmark the
fast image styles and the ReCoNet video model.

Image evaluation:

```bash
cd backend
python scripts/evaluate_style_transfer.py image \
  --input ../frontend/public/home/styled1.jpg \
  --style-id starry-night \
  --save-visualization evaluation/image-comparison.png \
  --json-out evaluation/image-metrics.json
```

Video evaluation with a saved temporal-stability graph:

```bash
cd backend
python scripts/evaluate_style_transfer.py video \
  --input path/to/input_video.mp4 \
  --save-output evaluation/stylized-video.mp4 \
  --save-plot evaluation/temporal-warping-error.png \
  --json-out evaluation/video-metrics.json
```

Notes:

* `LPIPS` is optional and only runs if you install it with `pip install lpips`.
* The video evaluator already computes an optical-flow-aligned temporal warping error,
  which is more meaningful than plain frame-to-frame difference for flicker checks.
* `--save-plot` writes a line graph of temporal warping error across frame pairs.

Example results table:

| Mode  | Checkpoint | Device | FPS | LPIPS | Temporal Warping Error (MAE) | Output |
|-------|------------|--------|-----|-------|-------------------------------|--------|
| Image | `models/starry/starry80.pth` | `cpu` | `2.97` | `N/A` | `N/A` | `evaluation/image-comparison.png` |
| Video | `style_transfer/reco/reconet.pth` | `cpu` | `1.25` | `N/A` | `0.0149` | `evaluation/temporal-warping-error.png` |

# Walkthrough(YouTube Video)
[![](https://img.youtube.com/vi/EddMbohoZZc/0.jpg)](https://www.youtube.com/watch?v=EddMbohoZZc)


# Credits
* Pretrained models were taken from https://github.com/zhanghang1989/PyTorch-Multi-Style-Transfer
