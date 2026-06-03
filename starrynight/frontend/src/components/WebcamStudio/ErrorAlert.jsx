import React from "react";

const ErrorAlert = ({ message, onRetry, retryLabel = "Retry" }) => {
  if (!message) {
    return null;
  }

  return (
    <div className="alert alert-danger mt-3 d-flex justify-content-between align-items-center flex-wrap">
      <span className="mr-2">{message}</span>
      {onRetry ? (
        <button type="button" className="btn btn-outline-light btn-sm mt-1 mt-sm-0" onClick={onRetry}>
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
};

export default ErrorAlert;
