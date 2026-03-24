import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const webRoot = path.resolve(__dirname, '..')
const repoRoot = path.resolve(webRoot, '..')

async function read(basePath, relativePath) {
  return readFile(path.join(basePath, relativePath), 'utf8')
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message)
  }
}

async function main() {
  const mainTsx = await read(webRoot, 'src/main.tsx')
  const workflow = await read(repoRoot, '.github/workflows/web-deploy.yml')
  const envExample = await read(repoRoot, '.env.example')

  assert(mainTsx.includes('AuthProvider'), 'Expected an AuthProvider in app bootstrap')
  assert(mainTsx.includes('ProtectedRoute'), 'Expected protected routes in app bootstrap')
  assert(mainTsx.includes('LoginPage'), 'Expected a login route in app bootstrap')
  assert(workflow.includes('VITE_SUPABASE_URL'), 'Expected optional frontend Supabase envs in Pages workflow')
  assert(envExample.includes('VITE_SUPABASE_URL'), 'Expected frontend Supabase envs in env example')

  console.log('Auth readiness checks passed')
}

main().catch((error) => {
  console.error(error.message)
  process.exitCode = 1
})
