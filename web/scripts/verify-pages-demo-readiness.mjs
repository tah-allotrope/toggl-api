import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const webRoot = path.resolve(__dirname, '..')

async function read(relativePath) {
  return readFile(path.join(webRoot, relativePath), 'utf8')
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message)
  }
}

async function main() {
  const mainTsx = await read('src/main.tsx')
  const viteConfig = await read('vite.config.ts')
  const supabaseLib = await read('src/lib/supabase.ts')

  assert(mainTsx.includes('HashRouter'), 'Expected HashRouter for GitHub Pages-safe routing')
  assert(viteConfig.includes("base: '/toggl-api/'"), 'Expected Vite base path for GitHub Pages repo deploy')
  assert(supabaseLib.includes('applyFilters('), 'Expected demo mode to share a reusable filter pipeline')
  assert(supabaseLib.includes("contains('tags', ['Highlight'])") === false, 'Mock verification script should inspect implementation, not component usage')
  assert(supabaseLib.includes('gte: ('), 'Expected demo query builder to support gte filters')
  assert(supabaseLib.includes('contains: ('), 'Expected demo query builder to support contains filters')
  assert(supabaseLib.includes('order: ('), 'Expected demo query builder to support order filters')

  console.log('Pages/demo readiness checks passed')
}

main().catch((error) => {
  console.error(error.message)
  process.exitCode = 1
})
