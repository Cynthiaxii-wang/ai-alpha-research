import { cp, access } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const root = new URL('../', import.meta.url)
const standalone = new URL('.next/standalone/', root)

try {
  await access(new URL('server.js', standalone))
} catch {
  console.error('缺少生产构建，请先运行 npm run build。')
  process.exit(1)
}

// Next.js standalone output omits these directories; include them for local hosting.
await cp(new URL('public/', root), new URL('public/', standalone), { recursive: true, force: true })
await cp(new URL('.next/static/', root), new URL('.next/static/', standalone), { recursive: true, force: true })
process.env.HOSTNAME = process.env.HOSTNAME || '0.0.0.0'
process.chdir(fileURLToPath(standalone))
await import(new URL('server.js', standalone).href)
