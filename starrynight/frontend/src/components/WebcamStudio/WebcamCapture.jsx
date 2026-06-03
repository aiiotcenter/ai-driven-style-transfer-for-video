import React, { useEffect, useRef, useState } from "react";

const WebcamCapture = ({
  onFrame,
  onStreamReady,
  captureInterval = 50,
  width = 640,
  height = 360,
  previewWidth = 640,
  previewHeight = 360,
}) => {
  const videoRef = useRef(null);
  const frameCanvasRef = useRef(null);
  const animationFrameRef = useRef(null);
  const lastFrameTimeRef = useRef(0);
  const [error, setError] = useState("");

  useEffect(() => {
    let stream = null;

    const start = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width,
            height,
            frameRate: {
              ideal: 10,
              max: 12,
            },
          },
          audio: false,
        });
        setError("");

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        if (onStreamReady) {
          onStreamReady(stream);
        }

        const drawLoop = (timestamp) => {
          const video = videoRef.current;
          const frameCanvas = frameCanvasRef.current;
          if (!video || !frameCanvas) {
            animationFrameRef.current = window.requestAnimationFrame(drawLoop);
            return;
          }
          if (timestamp - lastFrameTimeRef.current >= captureInterval && video.readyState >= 2) {
            const ctx = frameCanvas.getContext("2d");
            if (ctx) {
              ctx.drawImage(video, 0, 0, previewWidth, previewHeight);
              if (onFrame) {
                onFrame(frameCanvas);
              }
            }
            lastFrameTimeRef.current = timestamp;
          }
          animationFrameRef.current = window.requestAnimationFrame(drawLoop);
        };

        lastFrameTimeRef.current = 0;
        animationFrameRef.current = window.requestAnimationFrame(drawLoop);
      } catch (err) {
        setError("Webcam access denied or unavailable.");
      }
    };

    start();

    return () => {
      if (animationFrameRef.current) {
        window.cancelAnimationFrame(animationFrameRef.current);
      }
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      if (onStreamReady) {
        onStreamReady(null);
      }
    };
  }, [captureInterval, height, onFrame, onStreamReady, previewHeight, previewWidth, width]);

  return (
    <div>
      {error ? <div className="alert alert-danger">{error}</div> : null}
      <video
        ref={videoRef}
        playsInline
        muted
        autoPlay
        style={{ width: "100%", borderRadius: "8px" }}
      />
      <canvas
        ref={frameCanvasRef}
        width={previewWidth}
        height={previewHeight}
        style={{ display: "none" }}
      />
    </div>
  );
};

export default WebcamCapture;
