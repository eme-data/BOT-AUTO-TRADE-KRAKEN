import { useCallback, useEffect, useRef, useState } from 'react'

interface UseWebSocketReturn {
  lastMessage: unknown | null
  connected: boolean
  reconnect: () => void
}

export function useWebSocket(path: string): UseWebSocketReturn {
  const [lastMessage, setLastMessage] = useState<unknown | null>(null)
  const [connected, setConnected] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const unmountedRef = useRef(false)

  const getBackoff = useCallback(() => {
    const base = Math.min(1000 * Math.pow(2, retriesRef.current), 30000)
    return base
  }, [])

  const connect = useCallback(() => {
    if (unmountedRef.current) return

    // Build WebSocket URL from current location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}${path}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (unmountedRef.current) {
        ws.close()
        return
      }
      setConnected(true)
      retriesRef.current = 0
    }

    ws.onmessage = (event) => {
      if (unmountedRef.current) return
      try {
        const data = JSON.parse(event.data)
        // Ignore heartbeats — they keep the connection alive but are not data
        if (data && data.type === 'heartbeat') return
        setLastMessage(data)
      } catch {
        // Non-JSON message, ignore
      }
    }

    ws.onclose = () => {
      if (unmountedRef.current) return
      setConnected(false)
      wsRef.current = null

      // Auto-reconnect with exponential backoff
      const delay = getBackoff()
      retriesRef.current += 1
      reconnectTimerRef.current = setTimeout(() => {
        connect()
      }, delay)
    }

    ws.onerror = () => {
      // onclose will fire after onerror, so reconnect logic is handled there
    }
  }, [path, getBackoff])

  const reconnect = useCallback(() => {
    // Manual reconnect: reset backoff and reconnect immediately
    retriesRef.current = 0
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    connect()
  }, [connect])

  useEffect(() => {
    unmountedRef.current = false
    connect()

    return () => {
      unmountedRef.current = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  return { lastMessage, connected, reconnect }
}
