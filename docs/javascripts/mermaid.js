document$.subscribe(function () {
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "loose",
    theme: "base",
    themeVariables: {
      background: "#ffffff",
      mainBkg: "#e8f1ff",
      secondBkg: "#ecfeff",
      tertiaryColor: "#f8fafc",
      primaryColor: "#e8f1ff",
      primaryTextColor: "#0f172a",
      primaryBorderColor: "#1d4ed8",
      lineColor: "#0f4c81",
      secondaryColor: "#ecfeff",
      actorBkg: "#e8f1ff",
      actorBorder: "#1d4ed8",
      actorTextColor: "#0f172a",
      actorLineColor: "#1d4ed8",
      signalColor: "#0f4c81",
      signalTextColor: "#0f172a",
      labelBoxBkgColor: "#ecfeff",
      labelBoxBorderColor: "#0891b2",
      labelTextColor: "#0f172a",
      activationBkgColor: "#dbeafe",
      activationBorderColor: "#1d4ed8",
      noteBkgColor: "#f0f9ff",
      noteBorderColor: "#0ea5c6",
      noteTextColor: "#0f172a",
      loopTextColor: "#0f172a",
      sectionBkgColor: "#f8fafc",
      altSectionBkgColor: "#eff6ff",
      gridColor: "#bfdbfe",
      edgeLabelBackground: "#ecfeff",
      clusterBkg: "#f8fafc",
      clusterBorder: "#60a5fa",
      defaultLinkColor: "#0f4c81",
      titleColor: "#0f172a",
      nodeTextColor: "#0f172a",
      fontFamily:
        "Plus Jakarta Sans, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
    },
  });

  // MkDocs Material renders fenced Mermaid blocks as <pre class="mermaid"><code>...</code></pre>.
  // Convert to <div class="mermaid"> so Mermaid parses only diagram text.
  document.querySelectorAll("pre.mermaid").forEach(function (pre) {
    const code = pre.querySelector("code");
    const source = code ? code.textContent : pre.textContent;
    if (!source) return;

    const div = document.createElement("div");
    div.className = "mermaid";
    div.textContent = source.trim();
    pre.replaceWith(div);
  });

  mermaid.run({ querySelector: ".mermaid" });
});
