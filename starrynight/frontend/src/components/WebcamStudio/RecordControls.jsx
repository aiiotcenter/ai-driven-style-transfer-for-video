import React from "react";

const RecordControls = ({
  isRecording,
  recordingTimeMs,
  maxDurationMs = 30000,
  onStartRecording,
  onStopRecording,
  statusText,
  isProcessing,
  actionLabel,
  onAction,
  canAction,
}) => {
  const seconds = Math.floor(recordingTimeMs / 1000);
  const maxSeconds = Math.floor(maxDurationMs / 1000);

  return (
    <div className="mt-3">
      <div className="d-flex align-items-center flex-wrap">
        <button
          type="button"
          className="btn btn-success mr-2 mb-2"
          disabled={isRecording}
          onClick={onStartRecording}
        >
          Start Recording
        </button>
        <button
          type="button"
          className="btn btn-danger mr-2 mb-2"
          disabled={!isRecording}
          onClick={onStopRecording}
        >
          Stop Recording
        </button>
        {actionLabel && onAction ? (
          <button
            type="button"
            className="btn btn-primary mb-2"
            disabled={!canAction || isRecording || isProcessing}
            onClick={onAction}
          >
            {actionLabel}
          </button>
        ) : null}
      </div>
      <p className="mb-1">
        Record: {seconds}s / {maxSeconds}s
      </p>
      <p className="mb-1 text-muted">Best results: keep webcam clips short so processing can finish quickly.</p>
      <p className="mb-0">Status: {statusText}</p>
    </div>
  );
};

export default RecordControls;
