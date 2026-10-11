// A file attached in the opening chat -> lines Trip Understanding already reads: a place name or a link per line
// (src/trip/domain/resolve.py matches each one; a name it cannot match is kept as "chưa tìm thấy", never guessed).
// Read in the browser; nothing is uploaded but the text.

export const ACCEPT = '.txt,.md,.csv,.tsv,.json,.geojson,.kml,text/plain,text/csv,application/json'
export const MAX_FILE_BYTES = 2_000_000
const MAX_CHARS = 12_000 // the whole attachment text sent with one message
const URL_RE = /https?:\/\/\S+/g

export interface Attachment {
  name: string
  lines: string[]
}

// Google Takeout "Saved" lists are CSV (Title, Note, URL); "Saved Places.json" is GeoJSON; My Maps exports KML.
function fromCsv(raw: string, sep: string): string[] {
  const rows = raw.split(/\r?\n/).map((r) => r.split(sep).map((c) => c.trim().replace(/^"|"$/g, '')))
  const head = rows[0]?.map((c) => c.toLowerCase()) ?? []
  const nameAt = head.findIndex((c) => ['title', 'name', 'tên', 'ten'].includes(c))
  const body = nameAt >= 0 ? rows.slice(1) : rows
  return body.map((r) => {
    const url = r.find((c) => /^https?:\/\//.test(c))
    const name = r[nameAt >= 0 ? nameAt : 0]
    return (url && /0x[0-9a-f]+:0x[0-9a-f]+|\/video\/\d+/i.test(url) ? url : name || url || '').trim()
  })
}

function fromJson(raw: string): string[] {
  const out: string[] = []
  const walk = (v: unknown, key = '') => {
    if (typeof v === 'string') {
      if (/^https?:\/\//.test(v) || /^(name|title|place_name)$/i.test(key)) out.push(v)
    } else if (Array.isArray(v)) v.forEach((x) => walk(x, key))
    else if (v && typeof v === 'object') Object.entries(v).forEach(([k, x]) => walk(x, k))
  }
  walk(JSON.parse(raw))
  return out
}

const fromKml = (raw: string) => [...raw.matchAll(/<name>\s*(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?\s*<\/name>/gi)].map((m) => m[1]).slice(1) // the first <name> is the map's own

export async function readAttachment(file: File): Promise<Attachment> {
  if (file.size > MAX_FILE_BYTES) throw new Error('too big')
  const raw = await file.text()
  const ext = file.name.toLowerCase().split('.').pop() ?? ''
  let lines: string[]
  try {
    lines = ext === 'csv' ? fromCsv(raw, ',') : ext === 'tsv' ? fromCsv(raw, '\t') : ext === 'json' || ext === 'geojson' ? fromJson(raw) : ext === 'kml' ? fromKml(raw) : raw.split(/\r?\n/)
  } catch {
    lines = raw.match(URL_RE) ?? []
  }
  const seen = new Set<string>()
  lines = lines.map((l) => l.replace(/\s+/g, ' ').trim()).filter((l) => l && !seen.has(l) && seen.add(l))
  return { name: file.name, lines }
}

// The message the agent reads: what the user typed, then each file's lines under its name.
export function withAttachments(text: string, files: Attachment[]) {
  let out = text.trim()
  for (const f of files) out += `${out ? '\n\n' : ''}Danh sách từ file ${f.name}:\n${f.lines.join('\n')}`
  return out.length > MAX_CHARS ? out.slice(0, out.lastIndexOf('\n', MAX_CHARS)) : out
}
