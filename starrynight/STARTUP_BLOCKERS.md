# Startup Blockers Report

Generated: 2026-04-30

## Scope

I scanned the `starrynight` app, validated the main backend and frontend startup paths where possible, and separated:

- confirmed blockers in the current workspace
- code/config blockers that will fail once dependencies are installed
- non-startup issues that still make the app hard to use on first run

## Confirmed Blockers

### 1. Backend cannot start because no Python runtime dependencies are installed

Evidence:

- `python3 manage.py check` from `starrynight/backend` failed with `ModuleNotFoundError: No module named 'django'`
- the repo-local env `starrynight/.venv39` exists, but `pip list` only shows `pip`
- critical imports all fail in that env: `django`, `rest_framework`, `rest_framework_simplejwt`, `corsheaders`, `celery`, `redis`, `cv2`, `torch`

Impact:

- `manage.py runserver` cannot start at all

Exact fix:

1. Create and use a real project venv.
2. Install backend dependencies into that venv.
3. Do not rely on the checked-in `.venv39`; it is effectively empty.

Suggested commands:

```bash
cd starrynight
python3.9 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. The Python dependency set is not reproducible on a modern interpreter

Relevant files:

- `requirements.txt:1-10`
- `README.md:10-17`

Why this is a blocker:

- `torchvision==0.10.1+cu111` is a CUDA-specific build pin and is not a normal PyPI/macOS-friendly dependency.
- `torch` is unpinned, so even if install succeeds it may resolve to an incompatible version relative to `torchvision`.
- `numpy==1.19.5`, `opencv_python==4.5.1.48`, and the older Torch stack are from the Python 3.8/3.9 era.
- the README tells users to "Install python and node" but gives no supported versions.

Impact:

- a fresh install is likely to fail or become inconsistent on Python 3.11/3.12
- even when it installs, the ML stack may not match at runtime

Exact fix:

- Fast path: document and enforce Python 3.9 for the current stack.
- Better path: repin the ML stack to versions that support the intended current Python version.

Minimum documentation fix:

```text
Supported runtime:
- Python 3.9.x
- Node 16 or 18
```

Packaging fix:

- pin `torch` to the exact version that matches `torchvision`
- remove the CUDA-specific `+cu111` pin unless the install instructions also provide the required PyTorch wheel index and platform constraints

### 3. Frontend production build fails on Node 22

Relevant file:

- `frontend/package.json:19-25`

Evidence:

- `npm run build` failed under Node `v22.15.0` with `ERR_OSSL_EVP_UNSUPPORTED`
- `NODE_OPTIONS=--openssl-legacy-provider npm run build` succeeded

Cause:

- `react-scripts@4.0.3` uses an older Webpack toolchain that breaks on newer OpenSSL defaults in recent Node releases

Impact:

- the documented frontend startup path is environment-sensitive
- production builds are broken unless the user knows the workaround

Exact fix:

- Preferred: use Node 16 or Node 18 for this repo.
- Temporary workaround:

```bash
export NODE_OPTIONS=--openssl-legacy-provider
npm run build
```

- Longer-term fix: upgrade off `react-scripts@4`.

## Code And Config Blockers

These are not masked by opinion; they are visible in the code and will still matter after dependencies are installed.

### 4. `django-cors-headers` is used but not declared

Relevant files:

- `backend/writer_backend/settings.py:41-69`
- `requirements.txt:1-10`

Evidence:

- `INSTALLED_APPS` includes `corsheaders`
- `MIDDLEWARE` includes `corsheaders.middleware.CorsMiddleware`
- `requirements.txt` does not include `django-cors-headers`

Impact:

- Django setup will fail once imports are attempted in a clean environment

Exact fix:

Add this to `requirements.txt`:

```text
django-cors-headers
```

### 5. SimpleJWT blacklist models are imported, but the blacklist app is not installed

Relevant files:

- `backend/accounts/views.py:14-17`
- `backend/writer_backend/settings.py:41-52`

Evidence:

- `accounts/views.py` imports `rest_framework_simplejwt.token_blacklist.models`
- `INSTALLED_APPS` does not include `rest_framework_simplejwt.token_blacklist`

Impact:

- Django import/setup is likely to fail or the blacklist model usage will break at runtime
- if the blacklist app is enabled later, migrations will also be required

Exact fix:

Add this to `INSTALLED_APPS`:

```python
"rest_framework_simplejwt.token_blacklist",
```

Then run:

```bash
python manage.py migrate
```

### 6. The backend eagerly loads all style-transfer models during Django app import

Relevant file:

- `backend/style_transfer/apps.py:21-29`

Why this makes startup hard:

- model discovery uses a relative path: `scan_models('models/')`
- every `.pth` file is loaded during app import, before the first request
- this couples startup to current working directory, model presence, Torch availability, and machine memory

Impact:

- slow startup
- startup can fail on low-memory machines or from the wrong working directory
- hard to test and deploy outside `backend/`

Exact fix:

- resolve model paths from `BASE_DIR` instead of the process working directory
- lazy-load models on first use instead of during `AppConfig` import

### 7. The bundled end-to-end smoke script depends on `requests`, but `requirements.txt` does not declare it

Relevant files:

- `backend/scripts/e2e_webcam_smoke.py:1-13`
- `requirements.txt:1-10`

Impact:

- the documented smoke-test path is incomplete in a clean environment

Exact fix:

Add this to `requirements.txt`:

```text
requests
```

## First-Run Runtime Blockers

These do not stop the process from booting, but they make the program feel broken immediately.

### 8. Webcam flow still depends on Redis even when task mode is `thread`

Relevant files:

- `backend/writer_backend/settings.py:143-176`
- `backend/style_transfer/views.py:166-176`
- `backend/style_transfer/views.py:199-214`
- `backend/style_transfer/tasks.py:21-25`

Why this matters:

- docs say local development can use `WEBCAM_VIDEO_TASK_MODE=thread`
- but the default cache backend is still Redis
- the webcam job path uses `cache.set` and `cache.get`

Impact:

- webcam upload/status endpoints will still fail unless Redis is running or the cache backend is overridden

Exact fix:

For local no-Redis development, set:

```bash
export CACHE_BACKEND=file
```

or

```bash
export CACHE_BACKEND=locmem
```

If you want the distributed path, start Redis and Celery explicitly.

### 9. The image style-transfer UI requests the model list from a relative URL

Relevant file:

- `frontend/src/screens/StyleTransfer.js:30-37`

Evidence:

- `axios.get("style_transfer/models/")` is missing a leading slash
- the POST call just below correctly uses `/style_transfer/style/`

Impact:

- from the `/style_transfer` client route, the GET can resolve to the wrong path

Exact fix:

Change:

```js
axios.get("style_transfer/models/")
```

To:

```js
axios.get("/style_transfer/models/")
```

### 10. The frontend hardcodes `http://localhost:3000`

Relevant files:

- `frontend/src/components/Navbar.js:15-18`
- `frontend/src/utils.js:1-4`
- `backend/writer_backend/settings.py:28-37`

Impact:

- running the frontend on another host or via `127.0.0.1` is brittle
- logout/navigation behavior is tied to one origin
- CORS is only configured for `http://localhost:3000`, not `http://127.0.0.1:3000`

Exact fix:

- replace hardcoded absolute URLs with relative navigation
- add both localhost variants to CORS if local dev should support both

### 11. Model asset docs are inconsistent

Relevant files:

- `frontend/public/models/README.md:1-10`
- `frontend/src/screens/WebcamStudio.js:16-22`
- `scripts/verify_models.py:32-39`

Evidence:

- docs say the ONNX preview model should be `frontend/public/models/style_transfer.onnx`
- actual code expects `frontend/public/models/pointilism-10.onnx`
- the verification script also expects `pointilism-10.onnx`

Impact:

- easy to place the right file in the wrong path during setup

Exact fix:

- update the docs to match the actual runtime path, or update the runtime path to match the docs

## What Already Looks Good

- required model assets are present in this workspace:
  - `frontend/public/models/pointilism-10.onnx`
  - `backend/style_transfer/reco/reconet.pth`
- the browser ONNX runtime support files are present
- backend Python files compile successfully with `python3 -m compileall -q starrynight/backend`
- frontend build succeeds with the OpenSSL workaround, which confirms the app code is at least buildable

## Fastest Path To A Working Local Run

1. Use Python 3.9 and Node 16 or 18.
2. Create a fresh venv and install backend deps.
3. Add `django-cors-headers` to `requirements.txt`.
4. Add `"rest_framework_simplejwt.token_blacklist"` to `INSTALLED_APPS`.
5. Run `python manage.py migrate`.
6. For local webcam work without Redis, set `CACHE_BACKEND=file`.
7. Start Django from `starrynight/backend`.
8. Start the frontend with a Node version compatible with `react-scripts@4`.

Suggested dev session:

```bash
cd starrynight
python3.9 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cd backend
export CACHE_BACKEND=file
python manage.py migrate
python manage.py runserver

cd ../frontend
npm install
npm start
```

## Validation Notes

Commands that produced the most useful signals:

```bash
cd starrynight/backend
python3 manage.py check

cd ../frontend
npm run build
NODE_OPTIONS=--openssl-legacy-provider npm run build

cd ..
python3 scripts/verify_models.py
```

One validation limit:

- `npm start` could not be fully exercised in this sandbox because binding to `0.0.0.0` returned `listen EPERM: operation not permitted`
