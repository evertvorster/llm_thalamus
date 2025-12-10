#!/usr/bin/env python3

from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtCore import QUrl
import sys

html = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Local KaTeX test with base URL</title>

  <link rel="stylesheet"
        href="file:///usr/lib/node_modules/katex/dist/katex.min.css">
  <script src="file:///usr/lib/node_modules/katex/dist/katex.min.js"></script>
  <script src="file:///usr/lib/node_modules/katex/dist/contrib/auto-render.min.js"></script>
</head>
<body>
  <p>Below should be rendered by KaTeX:</p>
  <div>\[ E = mc^2 \]</div>   <!-- NOTE: single backslashes here -->

  <div id="status" style="margin-top:1em;font-family:monospace;"></div>

  <script>
    document.addEventListener("DOMContentLoaded", function () {
      var s = document.getElementById("status");
      s.innerHTML += "katex defined: " + (typeof katex !== "undefined") + "<br>";
      s.innerHTML += "renderMathInElement defined: " + (typeof renderMathInElement !== "undefined") + "<br>";

      if (typeof renderMathInElement === "function") {
        renderMathInElement(document.body, {
          delimiters: [
            {left: "\\[", right: "\\]", display: true},
            {left: "$$", right: "$$", display: true},
            {left: "$",  right: "$",  display: false}
          ],
          throwOnError: false
        });
        s.innerHTML += "renderMathInElement called<br>";
      } else {
        s.innerHTML += "renderMathInElement is NOT available.<br>";
      }
    });
  </script>
</body>
</html>
"""

app = QApplication(sys.argv)
view = QWebEngineView()

settings = view.settings()
settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)

# Crucial: treat page as local so file:/// scripts are allowed
view.setHtml(html, QUrl("file:///"))

view.resize(800, 600)
view.show()
app.exec()