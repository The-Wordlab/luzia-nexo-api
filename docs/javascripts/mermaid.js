document$.subscribe(function () {
  mermaid.initialize({
    startOnLoad: true,
    securityLevel: "loose",
    theme: "default",
  });
});
