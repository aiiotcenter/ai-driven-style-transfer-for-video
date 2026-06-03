import React from "react";

const ProcessingStatus = ({ jobId, status, progress, error }) => {
  if (!jobId) {
    return null;
  }

  const safeProgress = Math.max(0, Math.min(100, progress || 0));
  return (
    <div className="mt-3">
      <p className="mb-1">
        Job: <code>{jobId}</code>
      </p>
      <p className="mb-1">
        Processing status: <strong>{status}</strong>
      </p>
      <div className="progress mb-2" style={{ height: "10px" }}>
        <div
          className="progress-bar"
          role="progressbar"
          style={{ width: `${safeProgress}%` }}
          aria-valuenow={safeProgress}
          aria-valuemin="0"
          aria-valuemax="100"
        />
      </div>
      {error ? <div className="alert alert-danger py-1">{error}</div> : null}
    </div>
  );
};

export default ProcessingStatus;

