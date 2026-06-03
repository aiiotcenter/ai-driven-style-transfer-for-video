import React from "react";

const VideoComparison = ({
  originalUrl,
  processedUrl,
  onReset,
  originalLabel = "Original Capture",
  processedLabel = "Styled Capture",
  downloadLabel = "Download Styled Video",
}) => {
  if (!originalUrl && !processedUrl) {
    return null;
  }

  const renderVideo = (label, url, emptyText) => {
    if (!url) {
      return <p>{emptyText}</p>;
    }

    return (
      <>
        <video
          key={url}
          src={url}
          controls
          preload="metadata"
          style={{ width: "100%" }}
          onLoadedMetadata={(event) => {
            console.log(`${label} metadata loaded:`, {
              src: event.currentTarget.currentSrc || url,
              duration: event.currentTarget.duration,
              width: event.currentTarget.videoWidth,
              height: event.currentTarget.videoHeight,
            });
          }}
          onError={(event) => {
            console.error(`${label} video failed to load:`, {
              src: event.currentTarget.currentSrc || url,
              error: event.currentTarget.error,
            });
          }}
        />
        <small className="text-muted d-block mt-2" style={{ wordBreak: "break-all" }}>
          {label} source: {url}
        </small>
      </>
    );
  };

  return (
    <div className="mt-4">
      <div className="row">
        <div className="col-md-6 mb-3">
          <h6>{originalLabel}</h6>
          {renderVideo(originalLabel, originalUrl, "No input clip")}
        </div>
        <div className="col-md-6 mb-3">
          <h6>{processedLabel}</h6>
          {processedUrl ? (
            <>
              {renderVideo(processedLabel, processedUrl, "Not ready yet")}
              <a className="btn btn-outline-light btn-sm mt-2" href={processedUrl} download>
                {downloadLabel}
              </a>
            </>
          ) : (
            <p>Not ready yet</p>
          )}
        </div>
      </div>
      <button type="button" className="btn btn-secondary btn-sm" onClick={onReset}>
        Try Again
      </button>
    </div>
  );
};

export default VideoComparison;
