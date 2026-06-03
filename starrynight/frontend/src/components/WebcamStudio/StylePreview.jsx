import React, { useCallback, useEffect, useRef, useState } from "react";
import * as ort from "onnxruntime-web";

const StylePreview = ({
  modelUrl = "/models/pointilism-10.onnx",
  width = 640,
  height = 360,
  onCanvasReady,
  onProcessorReady,
  onStyledFrame,
}) => {
  const displayCanvasRef = useRef(null);
  const workingCanvasRef = useRef(null);
  const sessionRef = useRef(null);
  const isBusyRef = useRef(false);
  const [status, setStatus] = useState("loading");
  const [statusMessage, setStatusMessage] = useState("Loading ONNX preview model...");

  const createPreviewSession = useCallback(async () => {
    const providerAttempts = [
      { name: "webgl", executionProviders: ["webgl"] },
      { name: "wasm", executionProviders: ["wasm"] },
    ];
    const failures = [];

    for (const provider of providerAttempts) {
      try {
        const session = await ort.InferenceSession.create(modelUrl, {
          executionProviders: provider.executionProviders,
        });
        return { provider: provider.name, session };
      } catch (err) {
        failures.push(`${provider.name}: ${err?.message || "unknown error"}`);
      }
    }

    throw new Error(failures.join(" | "));
  }, [modelUrl]);

  const drawFallback = useCallback((sourceCanvas) => {
    const target = displayCanvasRef.current;
    if (!target || !sourceCanvas) {
      return;
    }
    const ctx = target.getContext("2d");
    if (!ctx) {
      return;
    }
    ctx.filter = "grayscale(1)";
    ctx.drawImage(sourceCanvas, 0, 0, width, height);
    ctx.filter = "none";
  }, [height, width]);

  const runModel = useCallback(async (sourceCanvas) => {
    const targetCanvas = displayCanvasRef.current;
    const session = sessionRef.current;
    if (!targetCanvas || !session) {
      drawFallback(sourceCanvas);
      return;
    }

    const inputName = session.inputNames[0];
    const outputName = session.outputNames[0];
    const dims = session.inputMetadata[inputName]?.dimensions || [];
    const inputHeight = Number.isInteger(dims[2]) ? dims[2] : height;
    const inputWidth = Number.isInteger(dims[3]) ? dims[3] : width;

    if (!workingCanvasRef.current) {
      workingCanvasRef.current = document.createElement("canvas");
    }
    const workingCanvas = workingCanvasRef.current;
    workingCanvas.width = inputWidth;
    workingCanvas.height = inputHeight;
    const workCtx = workingCanvas.getContext("2d");
    if (!workCtx) {
      drawFallback(sourceCanvas);
      return;
    }
    workCtx.drawImage(sourceCanvas, 0, 0, inputWidth, inputHeight);
    const imageData = workCtx.getImageData(0, 0, inputWidth, inputHeight).data;

    const chw = new Float32Array(3 * inputWidth * inputHeight);
    let offset = 0;
    for (let y = 0; y < inputHeight; y += 1) {
      for (let x = 0; x < inputWidth; x += 1) {
        const idx = (y * inputWidth + x) * 4;
        chw[offset] = imageData[idx] / 255.0;
        chw[offset + inputWidth * inputHeight] = imageData[idx + 1] / 255.0;
        chw[offset + 2 * inputWidth * inputHeight] = imageData[idx + 2] / 255.0;
        offset += 1;
      }
    }

    const inputTensor = new ort.Tensor("float32", chw, [1, 3, inputHeight, inputWidth]);
    const results = await session.run({ [inputName]: inputTensor });
    const output = results[outputName];

    const outDims = output.dims || [1, 3, inputHeight, inputWidth];
    const outData = output.data;
    const outHeight = Number.isInteger(outDims[2]) ? outDims[2] : inputHeight;
    const outWidth = Number.isInteger(outDims[3]) ? outDims[3] : inputWidth;

    const rgba = new Uint8ClampedArray(outWidth * outHeight * 4);
    const scale = outData.some((v) => v > 1.5) ? 1.0 : 255.0;
    for (let y = 0; y < outHeight; y += 1) {
      for (let x = 0; x < outWidth; x += 1) {
        const pixel = y * outWidth + x;
        const r = outData[pixel];
        const g = outData[pixel + outWidth * outHeight];
        const b = outData[pixel + 2 * outWidth * outHeight];
        const outIdx = pixel * 4;
        rgba[outIdx] = Math.max(0, Math.min(255, Math.round(r * scale)));
        rgba[outIdx + 1] = Math.max(0, Math.min(255, Math.round(g * scale)));
        rgba[outIdx + 2] = Math.max(0, Math.min(255, Math.round(b * scale)));
        rgba[outIdx + 3] = 255;
      }
    }

    const outCanvas = document.createElement("canvas");
    outCanvas.width = outWidth;
    outCanvas.height = outHeight;
    const outCtx = outCanvas.getContext("2d");
    if (!outCtx) {
      drawFallback(sourceCanvas);
      return;
    }
    outCtx.putImageData(new ImageData(rgba, outWidth, outHeight), 0, 0);

    const ctx = targetCanvas.getContext("2d");
    if (!ctx) {
      return;
    }
    ctx.drawImage(outCanvas, 0, 0, width, height);
  }, [drawFallback, height, width]);

  useEffect(() => {
    let mounted = true;
    const init = async () => {
      try {
        setStatus("loading");
        setStatusMessage("Loading live preview model...");
        ort.env.wasm.numThreads = 1;
        const { provider, session } = await createPreviewSession();
        if (!mounted) {
          return;
        }
        sessionRef.current = session;
        setStatus("ready");
        setStatusMessage(`Live preview ready (${provider})`);
      } catch (err) {
        if (!mounted) {
          return;
        }
        setStatus("fallback");
        setStatusMessage(err?.message || "ONNX preview unavailable, using fallback mode");
      }
    };
    init();
    return () => {
      mounted = false;
      sessionRef.current = null;
    };
  }, [createPreviewSession]);

  useEffect(() => {
    if (onCanvasReady) {
      onCanvasReady(displayCanvasRef.current);
    }
    return () => {
      if (onCanvasReady) {
        onCanvasReady(null);
      }
    };
  }, [onCanvasReady]);

  useEffect(() => {
    const processFrame = async (sourceCanvas) => {
      if (!sourceCanvas || isBusyRef.current) {
        return;
      }
      isBusyRef.current = true;
      try {
        if (sessionRef.current) {
          await runModel(sourceCanvas);
        } else {
          drawFallback(sourceCanvas);
        }
        if (onStyledFrame && displayCanvasRef.current) {
          onStyledFrame(displayCanvasRef.current);
        }
      } catch (err) {
        drawFallback(sourceCanvas);
      } finally {
        isBusyRef.current = false;
      }
    };
    if (onProcessorReady) {
      onProcessorReady(processFrame);
    }
    return () => {
      if (onProcessorReady) {
        onProcessorReady(null);
      }
    };
  }, [drawFallback, onProcessorReady, onStyledFrame, runModel]);

  return (
    <div>
      <canvas
        ref={displayCanvasRef}
        width={width}
        height={height}
        style={{ width: "100%", borderRadius: "8px", background: "#111" }}
      />
      <small className="text-muted">
        Live model status:{" "}
        {status === "loading"
          ? "Loading"
          : status === "ready"
            ? "Live ready"
            : "Fallback mode"}{" "}
        ({statusMessage})
      </small>
    </div>
  );
};

export default StylePreview;
