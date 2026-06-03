import React from "react";

const InlineSpinner = ({ label = "Loading..." }) => (
  <div className="d-flex align-items-center mt-2" role="status" aria-live="polite">
    <div className="spinner-border spinner-border-sm text-info mr-2" />
    <small>{label}</small>
  </div>
);

export default InlineSpinner;
