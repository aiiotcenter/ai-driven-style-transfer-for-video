import React, { useCallback, useEffect, useRef, useState } from "react";
import { Container } from "react-bootstrap";
import axios from "axios";

import AlertBox from "../components/AlertBox";
import WebcamCapture from "../components/WebcamStudio/WebcamCapture";
import StylePreview from "../components/WebcamStudio/StylePreview";
import RecordControls from "../components/WebcamStudio/RecordControls";
import VideoComparison from "../components/WebcamStudio/VideoComparison";
import InlineSpinner from "../components/WebcamStudio/InlineSpinner";
import ErrorAlert from "../components/WebcamStudio/ErrorAlert";
import ProcessingStatus from "../components/WebcamStudio/ProcessingStatus";

const CAPTURE_INTERVAL_MS = 50;
const MAX_RECORDING_MS = 10000;
const LIVE_CAPTURE_FPS = 15;
const STATUS_POLL_INTERVAL_MS = 2000;

const LIVE_STYLE_OPTIONS = [
  {
    id: "pointillism-live",
    label: "Pointillism Live",
    modelUrl: "/models/pointilism-10.onnx",
    description: "Live browser filter recorded directly from the styled canvas.",
  },
];

const selectMimeType = () => {
  const options = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
  for (const mimeType of options) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(mimeType)) {
      return mimeType;
    }
  }
  return "";
};

const normalizeWebcamStyles = (styles) =>
  (Array.isArray(styles) ? styles : [])
    .filter((style) => style && style.id)
    .map((style) => ({
      ...style,
      label: style.label || style.id,
      // Treat a missing `available` flag as usable so the UI does not go blank
      // if the backend payload shape drifts slightly.
      available: style.available !== false,
    }));

const WebcamStudio = () => {
  const [isAuth, setIsAuth] = useState(false);
  const [statusText, setStatusText] = useState("Live preview idle");
  const [errorText, setErrorText] = useState("");
  const [successText, setSuccessText] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTimeMs, setRecordingTimeMs] = useState(0);
  const [recordedVideoUrl, setRecordedVideoUrl] = useState("");
  const [liveStyledVideoUrl, setLiveStyledVideoUrl] = useState("");
  const [selectedStyle, setSelectedStyle] = useState(LIVE_STYLE_OPTIONS[0].id);
  const [webcamStyles, setWebcamStyles] = useState([]);
  const [isLoadingWebcamStyles, setIsLoadingWebcamStyles] = useState(true);
  const [selectedProcessingStyle, setSelectedProcessingStyle] = useState("");
  const [jobId, setJobId] = useState("");
  const [jobStatus, setJobStatus] = useState("idle");
  const [jobProgress, setJobProgress] = useState(0);
  const [jobError, setJobError] = useState("");
  const [processedVideoUrl, setProcessedVideoUrl] = useState("");

  const streamRef = useRef(null);
  const styledCanvasRef = useRef(null);
  const styleProcessorRef = useRef(null);
  const mediaRecordersRef = useRef({ raw: null, styled: null });
  const styledCaptureStreamRef = useRef(null);
  const recordingSessionRef = useRef(0);
  const rawChunksRef = useRef([]);
  const styledChunksRef = useRef([]);
  const timerRef = useRef(null);
  const rawVideoUrlRef = useRef("");
  const styledVideoUrlRef = useRef("");
  const processedVideoUrlRef = useRef("");
  const rawBlobRef = useRef(null);
  const styledBlobRef = useRef(null);

  useEffect(() => {
    if (localStorage.getItem("userToken") !== null) {
      setIsAuth(true);
    }
  }, []);

  useEffect(() => {
    let mounted = true;

    const loadWebcamStyles = async () => {
      setIsLoadingWebcamStyles(true);
      try {
        const response = await axios.get("/style_transfer/webcam-styles/");
        if (!mounted) {
          return;
        }
        const styles = normalizeWebcamStyles(response.data?.styles);
        const availableStyles = styles.filter((style) => style.available);
        const selectableStyles = availableStyles.length > 0 ? availableStyles : styles;
        const defaultStyle = response.data?.default_style || "";
        setWebcamStyles(selectableStyles);
        setSelectedProcessingStyle((current) => {
          if (current && selectableStyles.some((style) => style.id === current)) {
            return current;
          }
          if (defaultStyle && selectableStyles.some((style) => style.id === defaultStyle)) {
            return defaultStyle;
          }
          return selectableStyles[0]?.id || "";
        });
        setIsLoadingWebcamStyles(false);
      } catch (error) {
        console.error("WEBCAM STYLES LOAD FAILED:", error);
        if (!mounted) {
          return;
        }
        setWebcamStyles([]);
        setSelectedProcessingStyle("");
        setIsLoadingWebcamStyles(false);
        setErrorText("Could not load backend webcam styles.");
      }
    };

    loadWebcamStyles();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (jobId) {
      console.log("Job submitted:", jobId);
    }
  }, [jobId]);

  useEffect(() => {
    if (jobStatus !== "idle") {
      console.log("Status polled:", jobStatus, "progress:", jobProgress);
    }
  }, [jobProgress, jobStatus]);

  useEffect(() => {
    if (processedVideoUrl) {
      console.log("Video URL received:", processedVideoUrl);
    }
  }, [processedVideoUrl]);

  const updateVideoUrl = useCallback((urlRef, setter, blob) => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = "";
    }
    if (!blob) {
      setter("");
      return;
    }
    const nextUrl = URL.createObjectURL(blob);
    urlRef.current = nextUrl;
    setter(nextUrl);
  }, []);

  const setRemoteVideoUrl = useCallback((urlRef, setter, nextUrl) => {
    if (urlRef.current && urlRef.current.startsWith("blob:")) {
      URL.revokeObjectURL(urlRef.current);
    }
    urlRef.current = nextUrl || "";
    setter(nextUrl || "");
  }, []);

  const resolveBackendMediaUrl = useCallback((videoUrl) => {
    if (!videoUrl) {
      return "";
    }
    if (/^https?:\/\//i.test(videoUrl)) {
      return videoUrl;
    }

    const backendOrigin =
      window.location.port === "3000" ? "http://127.0.0.1:8000" : window.location.origin;
    return new URL(videoUrl, backendOrigin).toString();
  }, []);

  const resetProcessingState = useCallback(() => {
    setJobId("");
    setJobStatus("idle");
    setJobProgress(0);
    setJobError("");
    setRemoteVideoUrl(processedVideoUrlRef, setProcessedVideoUrl, "");
  }, [setRemoteVideoUrl]);

  const stopActiveRecorders = useCallback(() => {
    const { raw, styled } = mediaRecordersRef.current;
    if (raw && raw.state !== "inactive") {
      raw.stop();
    }
    if (styled && styled.state !== "inactive") {
      styled.stop();
    }
  }, []);

  useEffect(
    () => () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
      }
      stopActiveRecorders();
      if (styledCaptureStreamRef.current) {
        styledCaptureStreamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (rawVideoUrlRef.current) {
        URL.revokeObjectURL(rawVideoUrlRef.current);
      }
      if (styledVideoUrlRef.current) {
        URL.revokeObjectURL(styledVideoUrlRef.current);
      }
      if (processedVideoUrlRef.current && processedVideoUrlRef.current.startsWith("blob:")) {
        URL.revokeObjectURL(processedVideoUrlRef.current);
      }
    },
    [stopActiveRecorders]
  );

  const onStreamReady = useCallback((stream) => {
    streamRef.current = stream;
  }, []);

  const onStyledCanvasReady = useCallback((canvas) => {
    styledCanvasRef.current = canvas;
  }, []);

  const onProcessorReady = useCallback((processor) => {
    styleProcessorRef.current = processor;
  }, []);

  const onFrame = useCallback((frameCanvas) => {
    if (styleProcessorRef.current) {
      styleProcessorRef.current(frameCanvas);
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    stopActiveRecorders();
    setIsRecording(false);
    setStatusText("Finalizing live capture...");
  }, [stopActiveRecorders]);

  const startRecording = useCallback(() => {
    if (!streamRef.current) {
      setErrorText("Webcam stream is not ready yet.");
      return;
    }
    if (!styledCanvasRef.current || typeof styledCanvasRef.current.captureStream !== "function") {
      setErrorText("Styled canvas capture is not available in this browser.");
      return;
    }
    if (!window.MediaRecorder) {
      setErrorText("MediaRecorder is not supported in this browser.");
      return;
    }

    const mimeType = selectMimeType();
    const sessionId = Date.now();
    const recordingResult = {
      rawDone: false,
      styledDone: false,
      rawBlob: null,
      styledBlob: null,
    };

    const finalizeRecording = () => {
      if (!recordingResult.rawDone || !recordingResult.styledDone) {
        return;
      }
      mediaRecordersRef.current = { raw: null, styled: null };
      rawBlobRef.current = recordingResult.rawBlob;
      styledBlobRef.current = recordingResult.styledBlob;
      updateVideoUrl(rawVideoUrlRef, setRecordedVideoUrl, recordingResult.rawBlob);
      updateVideoUrl(styledVideoUrlRef, setLiveStyledVideoUrl, recordingResult.styledBlob);
      resetProcessingState();
      setStatusText("Live capture ready");
      setSuccessText("Your raw and live preview captures are ready. You can now process the raw clip at full quality.");
    };

    const buildRecorder = (stream, chunkRef, onStop) => {
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunkRef.current.push(event.data);
        }
      };
      recorder.onstop = onStop;
      return recorder;
    };

    setErrorText("");
    setSuccessText("");
    setStatusText("Recording live styled output...");
    setRecordingTimeMs(0);
    updateVideoUrl(rawVideoUrlRef, setRecordedVideoUrl, null);
    updateVideoUrl(styledVideoUrlRef, setLiveStyledVideoUrl, null);
    rawBlobRef.current = null;
    styledBlobRef.current = null;
    resetProcessingState();

    rawChunksRef.current = [];
    styledChunksRef.current = [];
    recordingSessionRef.current = sessionId;

    const styledStream = styledCanvasRef.current.captureStream(LIVE_CAPTURE_FPS);
    styledCaptureStreamRef.current = styledStream;

    const rawRecorder = buildRecorder(streamRef.current, rawChunksRef, () => {
      if (recordingSessionRef.current !== sessionId) {
        return;
      }
      recordingResult.rawBlob =
        rawChunksRef.current.length > 0
          ? new Blob(rawChunksRef.current, { type: rawRecorder.mimeType || "video/webm" })
          : null;
      recordingResult.rawDone = true;
      finalizeRecording();
    });

    const styledRecorder = buildRecorder(styledStream, styledChunksRef, () => {
      if (recordingSessionRef.current !== sessionId) {
        return;
      }
      styledStream.getTracks().forEach((track) => track.stop());
      styledCaptureStreamRef.current = null;
      recordingResult.styledBlob =
        styledChunksRef.current.length > 0
          ? new Blob(styledChunksRef.current, { type: styledRecorder.mimeType || "video/webm" })
          : null;
      recordingResult.styledDone = true;
      finalizeRecording();
    });

    mediaRecordersRef.current = {
      raw: rawRecorder,
      styled: styledRecorder,
    };

    rawRecorder.start(250);
    styledRecorder.start(250);
    setIsRecording(true);

    timerRef.current = window.setInterval(() => {
      setRecordingTimeMs((prev) => {
        const next = prev + CAPTURE_INTERVAL_MS;
        if (next >= MAX_RECORDING_MS) {
          stopRecording();
          return MAX_RECORDING_MS;
        }
        return next;
      });
    }, CAPTURE_INTERVAL_MS);
  }, [resetProcessingState, stopRecording, updateVideoUrl]);

  const submitForProcessing = useCallback(async () => {
    if (!rawBlobRef.current) {
      setErrorText("Record a webcam clip before requesting full-quality processing.");
      return;
    }
    if (!selectedProcessingStyle) {
      setErrorText("Choose a backend style before processing.");
      return;
    }

    const extension = rawBlobRef.current.type.includes("mp4") ? "mp4" : "webm";
    const uploadFileName = `webcam-recording.${extension}`;
    const formData = new FormData();
    formData.append("style", selectedProcessingStyle);
    formData.append("video", rawBlobRef.current, uploadFileName);

    try {
      setErrorText("");
      setJobError("");
      setSuccessText("");
      setStatusText("Uploading webcam clip for full-quality processing...");
      setJobStatus("queued");
      setJobProgress(0);
      setRemoteVideoUrl(processedVideoUrlRef, setProcessedVideoUrl, "");

      console.log("Submitting raw webcam clip:", {
        filename: uploadFileName,
        size: rawBlobRef.current.size,
        type: rawBlobRef.current.type,
        style: selectedProcessingStyle,
      });

      const response = await axios.post("/style_transfer/webcam-video/", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      console.log("Webcam upload response:", response.data);
      setJobId(response.data?.job_id || "");
      setJobStatus(response.data?.status || "queued");
      setJobProgress(0);
      setStatusText("Processing full-quality video...");
    } catch (error) {
      console.error("WEBCAM VIDEO SUBMIT FAILED:", error);
      setJobStatus("failed");
      setJobProgress(0);
      setJobError(error?.response?.data?.error || "Upload failed.");
      setStatusText("Upload failed");
    }
  }, [selectedProcessingStyle, setRemoteVideoUrl]);

  useEffect(() => {
    if (!jobId || jobStatus === "completed" || jobStatus === "failed") {
      return undefined;
    }

    let isCancelled = false;

    const pollJob = async () => {
      try {
        const response = await axios.get(`/style_transfer/video-status/${jobId}/`);
        console.log("Full status response:", JSON.stringify(response.data, null, 2));
        if (isCancelled) {
          return;
        }

        const status = response.data?.status || "queued";
        const progress = Number(response.data?.progress || 0);
        const error = response.data?.error || "";

        setJobStatus(status);
        setJobProgress(progress);
        setJobError(error);

        if (status === "completed") {
          const resolvedVideoUrl = resolveBackendMediaUrl(response.data?.video_url || "");
          setRemoteVideoUrl(processedVideoUrlRef, setProcessedVideoUrl, resolvedVideoUrl);
          setStatusText("Video Ready!");
          setSuccessText("Video Ready! You can preview or download the full-quality styled result.");
          return;
        }

        if (status === "failed") {
          setStatusText("Processing failed");
          return;
        }

        setStatusText(
          status === "queued"
            ? "Video queued for processing..."
            : `Processing... ${Math.max(0, Math.min(100, progress))}%`
        );
      } catch (error) {
        console.error("STYLED VIDEO STATUS POLL FAILED:", error);
        if (isCancelled) {
          return;
        }
        setJobError("Network error. Retry in 10s...");
      }
    };

    pollJob();
    const intervalId = window.setInterval(pollJob, STATUS_POLL_INTERVAL_MS);

    return () => {
      isCancelled = true;
      window.clearInterval(intervalId);
    };
  }, [jobId, jobStatus, resolveBackendMediaUrl, setRemoteVideoUrl]);

  const resetCapture = useCallback(() => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    stopActiveRecorders();
    if (styledCaptureStreamRef.current) {
      styledCaptureStreamRef.current.getTracks().forEach((track) => track.stop());
      styledCaptureStreamRef.current = null;
    }
    recordingSessionRef.current = 0;
    setStatusText("Live preview idle");
    setErrorText("");
    setSuccessText("");
    setIsRecording(false);
    setRecordingTimeMs(0);
    updateVideoUrl(rawVideoUrlRef, setRecordedVideoUrl, null);
    updateVideoUrl(styledVideoUrlRef, setLiveStyledVideoUrl, null);
    rawBlobRef.current = null;
    styledBlobRef.current = null;
    resetProcessingState();
  }, [resetProcessingState, stopActiveRecorders, updateVideoUrl]);

  const activeStyle = LIVE_STYLE_OPTIONS.find((option) => option.id === selectedStyle) || LIVE_STYLE_OPTIONS[0];
  const hasProcessingStyle = Boolean(selectedProcessingStyle);
  const canProcessFullQuality =
    Boolean(rawBlobRef.current) &&
    !isRecording &&
    jobStatus !== "processing" &&
    !isLoadingWebcamStyles &&
    hasProcessingStyle;

  return (
    <Container className="py-4">
      {isAuth !== true ? (
        <AlertBox variant="danger" children="login to continue" />
      ) : (
        <>
          <h2 className="mb-3">Live Webcam Studio</h2>
          <p className="text-muted mb-4">
            This mode keeps the filter live in your browser and records the styled canvas directly.
          </p>

          <div className="row">
            <div className="col-lg-6 mb-3">
              <h5>Camera Feed</h5>
              <WebcamCapture
                captureInterval={CAPTURE_INTERVAL_MS}
                onFrame={onFrame}
                onStreamReady={onStreamReady}
              />
            </div>
            <div className="col-lg-6 mb-3">
              <h5>Live Styled Output</h5>
              <StylePreview
                modelUrl={activeStyle.modelUrl}
                onCanvasReady={onStyledCanvasReady}
                onProcessorReady={onProcessorReady}
              />
            </div>
          </div>

          <RecordControls
            isRecording={isRecording}
            recordingTimeMs={recordingTimeMs}
            maxDurationMs={MAX_RECORDING_MS}
            onStartRecording={startRecording}
            onStopRecording={stopRecording}
            statusText={statusText}
            isProcessing={jobStatus === "queued" || jobStatus === "processing"}
            actionLabel="Process Full Quality"
            onAction={submitForProcessing}
            canAction={canProcessFullQuality}
          />

          <div className="mt-3">
            <label htmlFor="webcam-style-select" className="d-block mb-1">
              Live Style
            </label>
            <select
              id="webcam-style-select"
              className="form-control"
              value={selectedStyle}
              onChange={(event) => setSelectedStyle(event.target.value)}
              disabled={isRecording}
            >
              {LIVE_STYLE_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
            <small className="text-muted d-block mt-1">{activeStyle.description}</small>
          </div>

          <div className="mt-3">
            <label htmlFor="webcam-processing-style-select" className="d-block mb-1">
              Full Quality Style
            </label>
            <select
              id="webcam-processing-style-select"
              className="form-control"
              value={selectedProcessingStyle}
              onChange={(event) => setSelectedProcessingStyle(event.target.value)}
              disabled={isRecording || isLoadingWebcamStyles || webcamStyles.length === 0}
            >
              {isLoadingWebcamStyles ? <option value="">Loading backend styles...</option> : null}
              {!isLoadingWebcamStyles && webcamStyles.length === 0 ? (
                <option value="">No backend styles available</option>
              ) : null}
              {webcamStyles.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
            <small className="text-muted d-block mt-1">
              {isLoadingWebcamStyles
                ? "Loading the Django style catalog for final MP4 processing."
                : webcamStyles.length === 0
                  ? "No backend styles are available for full-quality processing right now."
                  : "This style is sent to Django for the final processed MP4."}
            </small>
          </div>

          {isRecording ? <InlineSpinner label="Capturing live styled video..." /> : null}
          {!isRecording && (jobStatus === "queued" || jobStatus === "processing") ? (
            <InlineSpinner label={`Processing... ${jobProgress}%`} />
          ) : null}

          <ProcessingStatus jobId={jobId} status={jobStatus} progress={jobProgress} error={jobError} />

          <ErrorAlert message={errorText || jobError} />

          {successText ? <AlertBox variant="success">{successText}</AlertBox> : null}

          <div className="mt-3 p-3 border rounded">
            <h6 className="mb-2">Debug Snapshot</h6>
            <small className="d-block text-muted" style={{ wordBreak: "break-all" }}>
              jobId: {jobId || "(empty)"}
            </small>
            <small className="d-block text-muted" style={{ wordBreak: "break-all" }}>
              jobStatus: {jobStatus}
            </small>
            <small className="d-block text-muted" style={{ wordBreak: "break-all" }}>
              recordedVideoUrl: {recordedVideoUrl || "(empty)"}
            </small>
            <small className="d-block text-muted" style={{ wordBreak: "break-all" }}>
              liveStyledVideoUrl: {liveStyledVideoUrl || "(empty)"}
            </small>
            <small className="d-block text-muted" style={{ wordBreak: "break-all" }}>
              processedVideoUrl: {processedVideoUrl || "(empty)"}
            </small>
          </div>

          {liveStyledVideoUrl ? (
            <div className="mt-4">
              <h6>Browser Live Preview Capture</h6>
              <video src={liveStyledVideoUrl} controls style={{ width: "100%" }} />
            </div>
          ) : null}

          <VideoComparison
            originalUrl={recordedVideoUrl}
            processedUrl={processedVideoUrl}
            originalLabel="Raw Camera Recording"
            processedLabel="Full-Quality Styled Video"
            downloadLabel="Download Video"
            onReset={resetCapture}
          />
        </>
      )}
    </Container>
  );
};

export default WebcamStudio;
