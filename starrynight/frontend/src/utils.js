const logout = () => {
  localStorage.removeItem("userToken");
  window.location.replace("/");
};
