export function resolveApiProxyTarget(env = process.env) {
  const target = env.VITE_API_PROXY_TARGET
  return target && target.trim() ? target.trim() : 'http://127.0.0.1:8080'
}
