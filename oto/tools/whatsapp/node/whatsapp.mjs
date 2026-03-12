import { makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } from '@whiskeysockets/baileys'
import { parseArgs } from 'node:util'
import { mkdirSync, rmSync, existsSync, readFileSync, writeFileSync } from 'node:fs'
import pino from 'pino'
import qrcode from 'qrcode-terminal'

const logger = pino({ level: 'silent' })

// --- Arg parsing ---

const command = process.argv[2]
if (!command) {
  output({ error: 'no_command', message: 'Usage: whatsapp.mjs <auth|send|list-chats|read> [options]' }, 1)
}

const { values: args } = parseArgs({
  args: process.argv.slice(3),
  options: {
    'auth-dir': { type: 'string', default: '' },
    to: { type: 'string' },
    message: { type: 'string' },
    chat: { type: 'string' },
    limit: { type: 'string', default: '20' },
  },
  strict: false,
})

const authDir = args['auth-dir']
if (!authDir) {
  output({ error: 'missing_arg', message: '--auth-dir is required' }, 1)
}

const storeFile = authDir + '/store.json'

// --- Helpers ---

function output(data, exitCode = 0) {
  process.stdout.write(JSON.stringify(data, null, 2) + '\n')
  process.exit(exitCode)
}

function toISO(ts) {
  if (!ts) return null
  const n = Number(ts)
  if (!n || !isFinite(n)) return null
  try { return new Date(n * 1000).toISOString() } catch { return null }
}

function normalizeJid(input) {
  if (input.includes('@')) return input
  let num = input.replace(/[\s\-\+\(\)]/g, '')
  if (/^0[67]\d{8}$/.test(num)) {
    num = '33' + num.slice(1)
  }
  return num + '@s.whatsapp.net'
}

function formatMessage(m) {
  const content = m.message
  let text = null
  let type = 'unknown'

  if (content?.conversation) { type = 'text'; text = content.conversation }
  else if (content?.extendedTextMessage?.text) { type = 'text'; text = content.extendedTextMessage.text }
  else if (content?.imageMessage) { type = 'image'; text = content.imageMessage.caption || null }
  else if (content?.videoMessage) { type = 'video'; text = content.videoMessage.caption || null }
  else if (content?.audioMessage) { type = 'audio' }
  else if (content?.documentMessage) { type = 'document'; text = content.documentMessage.fileName || null }
  else if (content?.stickerMessage) { type = 'sticker' }
  else if (content?.reactionMessage) { type = 'reaction'; text = content.reactionMessage.text }

  return {
    id: m.key.id,
    from: m.key.participant || m.key.remoteJid,
    from_me: m.key.fromMe || false,
    text,
    type,
    timestamp: toISO(m.messageTimestamp),
  }
}

// --- Simple store (persisted to JSON) ---

function isRealMessage(m) {
  return m.message && !m.message.protocolMessage && !m.message.senderKeyDistributionMessage
}

function loadStore() {
  const defaults = { chats: {}, messages: {}, contacts: {} }
  if (existsSync(storeFile)) {
    try { return { ...defaults, ...JSON.parse(readFileSync(storeFile, 'utf8')) } } catch {}
  }
  return defaults
}

function saveStore(store) {
  writeFileSync(storeFile, JSON.stringify(store))
}

function bindStore(sock, store) {
  sock.ev.on('messaging-history.set', ({ chats, messages }) => {
    try {
      for (const c of (chats || [])) {
        store.chats[c.id] = { ...store.chats[c.id], ...c }
      }
      for (const m of (messages || [])) {
        const jid = m.key?.remoteJid
        if (!jid || !isRealMessage(m)) continue
        if (!store.messages[jid]) store.messages[jid] = []
        if (!store.messages[jid].some(x => x.key?.id === m.key.id)) {
          store.messages[jid].push(m)
        }
      }
    } catch {}
  })
  sock.ev.on('chats.upsert', (chats) => {
    try {
      for (const c of chats) store.chats[c.id] = { ...store.chats[c.id], ...c }
    } catch {}
  })
  sock.ev.on('chats.update', (updates) => {
    try {
      for (const u of updates) {
        if (store.chats[u.id]) Object.assign(store.chats[u.id], u)
        else store.chats[u.id] = u
      }
    } catch {}
  })
  sock.ev.on('messages.upsert', ({ messages: msgs }) => {
    try {
      for (const m of msgs) {
        const jid = m.key?.remoteJid
        if (!jid || !isRealMessage(m)) continue
        if (!store.messages[jid]) store.messages[jid] = []
        if (!store.messages[jid].some(x => x.key?.id === m.key.id)) {
          store.messages[jid].push(m)
        }
        if (m.pushName) {
          const contactJid = m.key.participant || m.key.remoteJid
          store.contacts[contactJid] = m.pushName
        }
      }
    } catch {}
  })
}

// --- Connect ---

async function connect(showQR) {
  mkdirSync(authDir, { recursive: true })
  const { version } = await fetchLatestBaileysVersion()
  const store = loadStore()

  const maxRetries = showQR ? 5 : 1
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const { state, saveCreds } = await useMultiFileAuthState(authDir)
    const sock = makeWASocket({
      version,
      auth: state,
      logger,
      syncFullHistory: showQR,
    })
    sock.ev.on('creds.update', saveCreds)
    bindStore(sock, store)

    const result = await new Promise((resolve) => {
      const timeout = setTimeout(() => resolve({ status: 'timeout' }), showQR ? 120000 : 30000)
      sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
        if (qr && showQR) {
          qrcode.generate(qr, { small: true }, (code) => {
            process.stderr.write('\nScan this QR code with WhatsApp:\n' + code + '\n')
          })
        }
        if (connection === 'open') {
          clearTimeout(timeout)
          resolve({ status: 'open', sock })
        }
        if (connection === 'close') {
          clearTimeout(timeout)
          const code = lastDisconnect?.error?.output?.statusCode
          if (code === DisconnectReason.loggedOut) {
            resolve({ status: 'logged_out' })
          } else {
            resolve({ status: 'closed' })
          }
        }
      })
    })

    if (result.status === 'open') return { sock, store }
    if (result.status === 'logged_out') throw new Error('logged_out')
    if (result.status === 'timeout') throw new Error('connection_timeout')
    if (!showQR) throw new Error('not_authenticated')
    process.stderr.write('Reconnecting...\n')
  }
  throw new Error('connection_timeout')
}

// --- Commands ---

async function handleAuth() {
  if (existsSync(authDir)) {
    rmSync(authDir, { recursive: true })
  }
  const { sock, store } = await connect(true)
  const user = sock.user

  // Wait for history sync
  process.stderr.write('Waiting for history sync...\n')
  await new Promise((resolve) => {
    const timeout = setTimeout(resolve, 15000)
    sock.ev.on('messaging-history.set', ({ isLatest }) => {
      if (isLatest) { clearTimeout(timeout); setTimeout(resolve, 2000) }
    })
  })

  saveStore(store)
  const chatCount = Object.keys(store.chats).length
  process.stderr.write(`Synced ${chatCount} chats\n`)

  await sock.end()
  output({
    status: 'authenticated',
    phone: user?.id?.split(':')[0] || null,
    name: user?.name || null,
    chats_synced: chatCount,
  })
}

async function handleSend() {
  const to = args.to
  const message = args.message
  if (!to || !message) output({ error: 'missing_args', message: '--to and --message required' }, 1)

  const { sock, store } = await connect(false)
  const jid = normalizeJid(to)
  const result = await sock.sendMessage(jid, { text: message })
  await new Promise(resolve => setTimeout(resolve, 1000))
  saveStore(store)
  await sock.end()
  output({ status: 'sent', id: result.key.id, to: jid })
}

async function handleListChats() {
  const limit = parseInt(args.limit) || 20
  const { sock, store } = await connect(false)

  // Wait briefly for chat updates
  await new Promise(resolve => setTimeout(resolve, 2000))
  saveStore(store)

  const chats = Object.values(store.chats)
    .sort((a, b) => Number(b.conversationTimestamp || 0) - Number(a.conversationTimestamp || 0))
    .slice(0, limit)

  await sock.end()

  output({
    chats: chats.map(c => ({
      jid: c.id,
      name: c.name || c.subject || store.contacts[c.id] || c.id,
      unread: c.unreadCount || 0,
      last_message_at: toISO(c.conversationTimestamp),
      is_group: c.id.endsWith('@g.us'),
    }))
  })
}

async function handleRead() {
  const chat = args.chat
  if (!chat) output({ error: 'missing_args', message: '--chat required' }, 1)
  const limit = parseInt(args.limit) || 20
  const jid = normalizeJid(chat)

  const { sock, store } = await connect(false)

  // Wait briefly for new messages
  await new Promise(resolve => setTimeout(resolve, 2000))
  saveStore(store)

  const messages = (store.messages[jid] || [])
    .filter(isRealMessage)
    .sort((a, b) => Number(b.messageTimestamp || 0) - Number(a.messageTimestamp || 0))
    .slice(0, limit)

  await sock.end()

  output({ chat: jid, messages: messages.map(formatMessage) })
}

// --- Main ---

async function main() {
  try {
    switch (command) {
      case 'auth': await handleAuth(); break
      case 'send': await handleSend(); break
      case 'list-chats': await handleListChats(); break
      case 'read': await handleRead(); break
      default: output({ error: 'unknown_command', message: `Unknown command: ${command}` }, 1)
    }
  } catch (err) {
    const msg = err.message || String(err)
    process.stderr.write(err.stack + '\n')
    if (msg === 'not_authenticated' || msg === 'logged_out') {
      output({ error: msg, message: 'Run: oto whatsapp auth' }, 1)
    } else {
      output({ error: 'error', message: msg }, 1)
    }
  }
}

main()
