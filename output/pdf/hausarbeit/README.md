# LaTeX-Arbeitsfassung

Dieser Ordner enthält die LaTeX-basierte PDF-Fassung von `Hausarbeit.md`.

Zum erneuten Erzeugen der PDF im Repository-Root ausführen:

```sh
output/pdf/hausarbeit/build.sh
```

Das Skript erzeugt `Hausarbeit-content.md` aus der aktuellen Markdown-Datei,
kompiliert `Hausarbeit.tex` mit LuaLaTeX und schreibt die fertige Datei als
`Hausarbeit.pdf` in diesen Ordner. Temporäre LaTeX-Dateien liegen unter
`tmp/pdfs/hausarbeit/`.
