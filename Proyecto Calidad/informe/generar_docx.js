// Genera informe.docx a partir de informe.md, con un recuadro donde va cada captura.
//
// Uso (desde esta carpeta):
//   npm install docx
//   node generar_docx.js
//
// Entiende el Markdown que usa informe.md: títulos (#, ##, ###), párrafos, listas (- y 1.), tablas, **negrita**,
// `código`, la portada (<div class="portada">) y las marcas de captura:
//   <!-- CAPTURA 01 | qué capturar | de dónde sacarla -->
const fs = require("fs");
const path = require("path");
const {
  AlignmentType, BorderStyle, Document, HeadingLevel, LevelFormat, Packer, PageBreak, Paragraph, ShadingType,
  Table, TableCell, TableRow, TextRun, WidthType, Footer, PageNumber, ImageRun,
} = require("docx");

const AQUI = __dirname;
const ANCHO = 9638;            // A4 (11906) menos márgenes de 2 cm (1134 por lado), en DXA
const AZUL = "2B4C7E";
const FUENTE = "Calibri";

// ── Texto con **negrita** y `código` ────────────────────────────────────────────────────────────────────
function runs(texto, base = {}) {
  const partes = texto.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return partes.map((p) => {
    if (p.startsWith("**") && p.endsWith("**")) return new TextRun({ ...base, text: p.slice(2, -2), bold: true });
    if (p.startsWith("`") && p.endsWith("`")) return new TextRun({ ...base, text: p.slice(1, -1), font: "Consolas", size: 18 });
    return new TextRun({ ...base, text: p });
  });
}

// ── Tablas ─────────────────────────────────────────────────────────────────────────────────────────────
const celdas = (linea) => linea.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
const borde = { style: BorderStyle.SINGLE, size: 4, color: "B9C4D4" };
const bordes = { top: borde, bottom: borde, left: borde, right: borde };

function tabla(lineas) {
  const filas = lineas.filter((l, i) => i !== 1).map(celdas);
  const n = filas[0].length;
  // Ancho de cada columna proporcional al texto más largo (con un mínimo), sumando exactamente ANCHO.
  const largo = Array.from({ length: n }, (_, j) => Math.max(6, ...filas.map((f) => Math.min(60, (f[j] || "").length))));
  const total = largo.reduce((a, b) => a + b, 0);
  const anchos = largo.map((l) => Math.max(900, Math.round((l / total) * ANCHO)));
  anchos[n - 1] += ANCHO - anchos.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: ANCHO, type: WidthType.DXA },
    columnWidths: anchos,
    rows: filas.map((f, i) => new TableRow({
      tableHeader: i === 0,
      cantSplit: true,
      children: anchos.map((w, j) => new TableCell({
        width: { size: w, type: WidthType.DXA },
        borders: bordes,
        shading: i === 0 ? { type: ShadingType.CLEAR, fill: "E8EEF7", color: "auto" } : undefined,
        margins: { top: 50, bottom: 50, left: 90, right: 90 },
        children: [new Paragraph({ spacing: { after: 0 }, children: runs(f[j] || "", { size: 18, bold: i === 0 }) })],
      })),
    })),
  });
}

// ── Recuadro para pegar una captura ────────────────────────────────────────────────────────────────────
function imagenDe(numero) {
  for (const ext of ["png", "jpg", "jpeg"]) {
    const f = path.join(AQUI, "capturas", `${numero}.${ext}`);
    if (fs.existsSync(f)) return { f, ext: ext === "jpeg" ? "jpg" : ext };
  }
  return null;
}

// Tamaño en píxeles de un PNG (cabecera IHDR) o JPG (marcador SOF), para respetar la proporción.
function tamano(f, ext) {
  const b = fs.readFileSync(f);
  if (ext === "png") return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
  let i = 2;
  while (i < b.length) {
    const m = b[i + 1];
    if (m >= 0xc0 && m <= 0xc3) return { h: b.readUInt16BE(i + 5), w: b.readUInt16BE(i + 7) };
    i += 2 + b.readUInt16BE(i + 2);
  }
  return { w: 800, h: 600 };
}

function figura(f, ext, numero, que) {
  const { w, h } = tamano(f, ext);
  const ancho = Math.min(600, w);                       // 600 px ≈ ancho útil de la página
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, keepNext: true,
    children: [new ImageRun({ type: ext, data: fs.readFileSync(f),
      transformation: { width: ancho, height: Math.round((ancho * h) / w) },
      altText: { title: `Captura ${numero}`, description: que, name: `captura-${numero}` } })] });
}

function captura(numero, que, donde) {
  const img = imagenDe(numero);
  if (img) {
    const { w, h } = tamano(img.f, img.ext);
    const ancho = Math.min(600, w);                       // 600 px ≈ ancho útil de la página
    return [
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 0 }, keepNext: true,
        children: [new ImageRun({ type: img.ext, data: fs.readFileSync(img.f),
          transformation: { width: ancho, height: Math.round((ancho * h) / w) },
          altText: { title: `Captura ${numero}`, description: que, name: `captura-${numero}` } })] }),
      new Paragraph({ spacing: { before: 60, after: 200 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: `Figura ${numero}. ${que}`, italics: true, size: 18, color: "555555" })] }),
    ];
  }
  const punteado = { style: BorderStyle.DASHED, size: 12, color: AZUL, space: 6 };
  const caja = { top: punteado, bottom: punteado, left: punteado, right: punteado };
  const p = (children, extra = {}) => new Paragraph({
    border: caja, shading: { type: ShadingType.CLEAR, fill: "F3F6FB", color: "auto" },
    alignment: AlignmentType.CENTER, spacing: { before: 0, after: 0 }, keepNext: true, keepLines: true, children, ...extra,
  });
  return [
    p([new TextRun({ text: `PEGAR AQUÍ LA CAPTURA ${numero}`, bold: true, color: AZUL, size: 22 })], { spacing: { before: 200, after: 0 } }),
    p([new TextRun({ text: que, size: 20 })]),
    p([new TextRun({ text: "De dónde: ", bold: true, size: 18, color: "555555" }), new TextRun({ text: donde, size: 18, color: "555555" })]),
    p([new TextRun({ text: " ", size: 40 })]),
    p([new TextRun({ text: " ", size: 40 })]),
    new Paragraph({ spacing: { before: 60, after: 200 }, alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: `Figura ${numero}. ${que}`, italics: true, size: 18, color: "555555" })] }),
  ];
}

// ── Markdown → bloques de docx ─────────────────────────────────────────────────────────────────────────
function convertir(md) {
  const lineas = md.replace(/\r/g, "").split("\n");
  const hijos = [];
  let i = 0;
  let parrafo = [];
  let marcaActual = null;
  const cerrarParrafo = () => {
    if (parrafo.length) hijos.push(new Paragraph({ spacing: { after: 120 }, children: runs(parrafo.join(" ")) }));
    parrafo = [];
  };
  while (i < lineas.length) {
    const l = lineas[i];
    const marca = l.match(/^<!-- CAPTURA (\d+) \| (.+?) \| (.+?) -->$/);
    const imgMd = l.match(/^!\[(.*?)\]\((.+?)\)$/);
    if (l.startsWith('<div class="portada"')) {
      cerrarParrafo();
      i++;
      const portada = [];
      while (!lineas[i].startsWith("</div>")) { if (lineas[i].trim()) portada.push(lineas[i].trim()); i++; }
      hijos.push(new Paragraph({ spacing: { before: 3600 }, children: [] }));
      for (const t of portada) {
        if (t.startsWith("# ")) hijos.push(new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: t.slice(2), bold: true, size: 52, color: AZUL })] }));
        else if (t.startsWith("## ")) hijos.push(new Paragraph({ spacing: { after: 600 }, children: [new TextRun({ text: t.slice(3), bold: true, size: 30 })] }));
        else hijos.push(new Paragraph({ spacing: { after: 100 }, children: runs(t, { size: 23 }) }));
      }
      hijos.push(new Paragraph({ children: [new PageBreak()] }));
    } else if (imgMd) {
      // Imagen puesta a mano en el markdown, justo después de la marca de captura.
      cerrarParrafo();
      const f = path.resolve(AQUI, decodeURI(imgMd[2]));
      const ext = path.extname(f).slice(1).toLowerCase().replace("jpeg", "jpg");
      if (fs.existsSync(f)) hijos.push(figura(f, ext, imgMd[1], marcaActual ? marcaActual.que : imgMd[1]));
      const sigue = lineas.slice(i + 1).find((x) => x.trim() !== "");
      if (!sigue || !sigue.startsWith("![")) {
        if (marcaActual) hijos.push(new Paragraph({ spacing: { before: 60, after: 200 }, alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: `Figura ${marcaActual.numero}. ${marcaActual.que}`, italics: true, size: 18, color: "555555" })] }));
        marcaActual = null;
      }
    } else if (marca) {
      cerrarParrafo();
      const sig = lineas.slice(i + 1).find((x) => x.trim() !== "");
      if (sig && sig.startsWith("![")) marcaActual = { numero: marca[1], que: marca[2] };   // la imagen ya está en el markdown
      else hijos.push(...captura(marca[1], marca[2], marca[3]));
    } else if (/^#{1,3} /.test(l)) {
      cerrarParrafo();
      const nivel = l.match(/^#+/)[0].length;
      hijos.push(new Paragraph({
        heading: [HeadingLevel.HEADING_1, HeadingLevel.HEADING_1, HeadingLevel.HEADING_2][nivel - 1] ?? HeadingLevel.HEADING_2,
        children: [new TextRun(l.replace(/^#+ /, ""))],
      }));
    } else if (l.startsWith("|")) {
      cerrarParrafo();
      const bloque = [];
      while (i < lineas.length && lineas[i].startsWith("|")) bloque.push(lineas[i++]);
      hijos.push(tabla(bloque));
      hijos.push(new Paragraph({ spacing: { after: 60 }, children: [] }));
      continue;
    } else if (/^(- |\d+\. )/.test(l)) {
      cerrarParrafo();
      const numerada = /^\d+\. /.test(l);
      let texto = l.replace(/^(- |\d+\. )/, "");
      while (i + 1 < lineas.length && /^ {2,}\S/.test(lineas[i + 1]) && !/^\s*- /.test(lineas[i + 1])) texto += " " + lineas[++i].trim();
      hijos.push(new Paragraph({ numbering: { reference: numerada ? "numeros" : "vinetas", level: 0 }, spacing: { after: 60 }, children: runs(texto) }));
      while (i + 1 < lineas.length && /^ {2,}- /.test(lineas[i + 1])) {
        let sub = lineas[++i].trim().replace(/^- /, "");
        while (i + 1 < lineas.length && /^ {4,}\S/.test(lineas[i + 1]) && !/^\s*- /.test(lineas[i + 1])) sub += " " + lineas[++i].trim();
        hijos.push(new Paragraph({ numbering: { reference: "vinetas", level: 1 }, spacing: { after: 60 }, children: runs(sub) }));
      }
    } else if (!l.trim() || l.startsWith("<!--") || l.startsWith("</div>")) {
      cerrarParrafo();
    } else {
      parrafo.push(l.trim());
    }
    i++;
  }
  cerrarParrafo();
  return hijos;
}

const md = fs.readFileSync(path.join(AQUI, "informe.md"), "utf8");
const doc = new Document({
  creator: "OptiFull",
  title: "Calidad de Software aplicada al TFG - Informe",
  styles: {
    default: { document: { run: { font: FUENTE, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, color: AZUL, font: FUENTE },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0, keepNext: true,
          border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: AZUL, space: 2 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: AZUL, font: FUENTE },
        paragraph: { spacing: { before: 240, after: 80 }, outlineLevel: 1, keepNext: true } },
    ],
  },
  numbering: {
    config: [
      { reference: "vinetas", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 540, hanging: 270 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 1080, hanging: 270 } } } },
      ] },
      { reference: "numeros", levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 540, hanging: 300 } } } },
      ] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "777777" })] })] }) },
    children: convertir(md),
  }],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(path.join(AQUI, "informe.docx"), buffer);
  console.log("Listo:", path.join(AQUI, "informe.docx"));
});
