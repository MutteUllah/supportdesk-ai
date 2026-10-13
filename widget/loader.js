(() => {
  const script = document.currentScript;
  const workspace = script?.dataset.workspace;
  if (!workspace) return;
  const api = new URL(script.src).origin;
  const button = document.createElement("button");
  button.textContent = "Chat with support";
  button.setAttribute("aria-expanded", "false");
  Object.assign(button.style, {
    position: "fixed",
    bottom: "22px",
    right: "22px",
    border: "0",
    borderRadius: "28px",
    padding: "16px 22px",
    background: "#176b5b",
    color: "white",
    font: "600 14px Arial",
    cursor: "pointer",
    zIndex: "2147483000",
    boxShadow: "0 5px 24px #0003",
  });
  const iframe = document.createElement("iframe");
  iframe.title = "Customer support chat";
  iframe.src = `${api}/widget/${encodeURIComponent(workspace)}#${encodeURIComponent(location.origin)}`;
  iframe.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
  iframe.referrerPolicy = "origin";
  Object.assign(iframe.style, {
    position: "fixed",
    bottom: "85px",
    right: "22px",
    width: "min(390px, calc(100vw - 24px))",
    height: "min(620px, calc(100dvh - 110px))",
    border: "1px solid #dce5df",
    borderRadius: "16px",
    background: "white",
    boxShadow: "0 10px 60px #0003",
    zIndex: "2147483000",
    display: "none",
  });
  button.onclick = () => {
    const open = iframe.style.display === "none";
    iframe.style.display = open ? "block" : "none";
    button.setAttribute("aria-expanded", String(open));
    button.textContent = open ? "Close support" : "Chat with support";
  };
  document.body.append(iframe, button);
})();
