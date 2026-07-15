type Context = Record<string, unknown>

const PREFIX = '[citygml-browser]'

function withContext(message: string, context?: Context): string {
  if (!context) return `${PREFIX} ${message}`
  return `${PREFIX} ${message} ${JSON.stringify(context)}`
}

export const logger = {
  info(message: string, context?: Context): void {
    console.info(withContext(message, context))
  },
  warn(message: string, context?: Context): void {
    console.warn(withContext(message, context))
  },
  error(message: string, context?: Context): void {
    console.error(withContext(message, context))
  },
}
