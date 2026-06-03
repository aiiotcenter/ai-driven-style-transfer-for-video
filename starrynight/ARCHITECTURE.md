# StarryNight Architecture (One Page)

```mermaid
flowchart LR
    U[User Browser]

    subgraph FE[React Frontend (frontend/src)]
        APP[App Router<br/>/ /login /signup /style_transfer]
        NAV[Navbar + localStorage auth check]
        ST[StyleTransfer screen]
        LG[Login screen]
        SG[Signup screen]
        CAR[Styled results carousel]
    end

    subgraph BE[Django Backend (backend)]
        ROOT[writer_backend urls.py]

        subgraph ACC[accounts app]
            A1[POST /accounts/login/]
            A2[POST /accounts/register/]
            A3[JWT serializers/views]
        end

        subgraph STF[style_transfer app]
            S1[GET /style_transfer/models/]
            S2[POST /style_transfer/style/]
            S3[uploadImage view]
            S4[StyleTransferConfig model preload]
            S5[fast_style.api stlye_transfer]
            S6[fast_style.stylize]
            S7[TransformerNetwork (PyTorch)]
        end
    end

    subgraph MDL[Model Assets]
        M1[backend/models/**/*.pth]
    end

    U --> APP
    APP --> NAV

    U --> LG
    LG --> A1 --> A3
    A3 --> LG
    LG -->|stores JWT in localStorage| NAV

    U --> SG
    SG --> A2 --> A3

    U --> ST
    ST -->|1) GET available models| S1
    S1 --> ST
    ST -->|2) POST image + selected styles| S2
    S2 --> S3 --> S5 --> S6 --> S7
    S7 -->|styled image arrays| S3
    S3 -->|base64 PNGs (per model)| ST --> CAR

    ROOT --> ACC
    ROOT --> STF
    M1 --> S4 --> S2
```

```mermaid
flowchart TB
    subgraph Repo[Repository: neural-style-video]
        subgraph SN[starrynight (deployed web app path)]
            SNFE[React SPA]
            SNBE[Django REST + JWT]
            SNPY[Fast style transfer inference]
        end

        subgraph RC[Real-time-Coherent-Style-Transfer-For-Videos (standalone research)]
            RCN[ReCoNet architecture]
            RCT[train.py + temporal/style/content losses]
            RCI[infer.py video loop]
            RCD[MPI + FlyingChairs dataset loaders]
        end
    end

    SNFE --> SNBE --> SNPY
    RCT --> RCN --> RCI
    RCD --> RCT
    RC -. not wired to StarryNight runtime APIs .- SN
```

## Request Arrow Summary

- `Browser -> React -> GET /style_transfer/models/ -> Django style_transfer`
- `Browser -> React -> POST /style_transfer/style/ -> uploadImage -> fast_style -> PyTorch model -> base64 images -> React carousel`
- `Browser -> React Login/Signup -> /accounts/* -> JWT -> localStorage -> gated style-transfer UI`

## Phase 1 Runtime Checklist

### Required Model Assets

- ONNX preview model: `frontend/public/models/pointilism-10.onnx`
- Default ReCoNet checkpoint: `backend/style_transfer/reco/reconet.pth`
- Optional multi-style ReCoNet checkpoints: `backend/style_transfer/reco/styles/<style-id>.pth`

Optional explicit style mapping:

```bash
export RECONET_STYLE_MODELS="starry-night=/abs/path/starry.pth,mosaic=/abs/path/mosaic.pth"
```

Verify both files before runtime:

```bash
python3.11 scripts/verify_models.py
```

### End-to-End Smoke Flow

Run from `starrynight/backend`:

For local development, webcam jobs default to `WEBCAM_VIDEO_TASK_MODE=thread` while `DEBUG=True`, so `python3.11 manage.py runserver` is enough to exercise uploads end to end. Switch to Celery explicitly when you want the distributed worker path:

```bash
export WEBCAM_VIDEO_TASK_MODE=celery
```

Only the Celery mode needs Redis + a worker:

```bash
# ensure shared status cache across Django + Celery
export CACHE_BACKEND=redis
export CACHE_URL=redis://127.0.0.1:6379/1
```

```bash
# terminal 1
redis-server
```

```bash
# terminal 2
celery -A writer_backend worker -l info
```

```bash
# terminal 3
python3.11 manage.py runserver
```

```bash
# terminal 4 (API-level webcam smoke without browser)
python3.11 scripts/e2e_webcam_smoke.py --base-url http://127.0.0.1:8000
```

Webcam style metadata endpoint:

```bash
GET /style_transfer/webcam-styles/
```

### Expected Error Surfaces

- Upload guardrail: `File too large (max 100MB)`
- Unsupported input codec: `Processing failed: unsupported or corrupted video codec.`
- GPU memory pressure: `Processing failed: GPU out of memory.`
- Polling network failures in UI: `Network error. Retry in 10s...`
