Place the lightweight preview ONNX model here:

- Expected path: `frontend/public/models/pointilism-10.onnx`
- Suggested source: ONNX fast neural style transfer model (about 5-10MB)
- Runtime assets for `onnxruntime-web` should also live here, including `ort-wasm.wasm`
  and `ort-wasm-threaded.wasm`, so the webcam preview can initialize in the browser.
  For this Create React App setup, mirror those runtime files under `frontend/public/static/js/`
  as well because `onnxruntime-web@1.8.0` resolves them relative to the bundle path.

The webcam preview component falls back to grayscale if the model is missing.
