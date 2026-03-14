import { useCallback, useEffect, useRef } from 'react'

/**
 * Hook that requests notification permission and provides a `notify()` function.
 * Notifications are shown as native OS/PWA notifications.
 */
export function useNotifications() {
  const permissionRef = useRef<NotificationPermission>('default')

  useEffect(() => {
    if (!('Notification' in window)) return
    permissionRef.current = Notification.permission
    if (Notification.permission === 'default') {
      Notification.requestPermission().then(p => {
        permissionRef.current = p
      })
    }
  }, [])

  const notify = useCallback((title: string, body: string, tag?: string) => {
    if (!('Notification' in window)) return
    if (permissionRef.current !== 'granted') return

    // Use service worker registration if available (for PWA)
    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
      navigator.serviceWorker.ready.then(reg => {
        reg.showNotification(title, {
          body,
          tag: tag || 'altior-bot',
          icon: '/pwa-192x192.png',
          badge: '/pwa-192x192.png',
        } as NotificationOptions)
      }).catch(() => {
        // Fallback to regular notification
        new Notification(title, { body, tag: tag || 'altior-bot' })
      })
    } else {
      new Notification(title, { body, tag: tag || 'altior-bot' })
    }
  }, [])

  return { notify }
}


/**
 * Hook that listens to WebSocket trade events and fires notifications.
 * Pass the lastMessage from the dashboard WebSocket.
 */
export function useTradeNotifications(lastMessage: unknown) {
  const { notify } = useNotifications()
  const processedRef = useRef(new Set<string>())

  useEffect(() => {
    if (!lastMessage || typeof lastMessage !== 'object') return
    const msg = lastMessage as Record<string, unknown>

    // Trade opened notification
    if (msg.type === 'trade_opened') {
      const key = `open_${msg.pair}_${msg.price}`
      if (processedRef.current.has(key)) return
      processedRef.current.add(key)
      notify(
        `Trade ouvert: ${msg.pair}`,
        `${String(msg.direction).toUpperCase()} ${msg.size} @ $${msg.price}\nStrategie: ${msg.strategy || 'auto'}`,
        `trade_${key}`,
      )
    }

    // Trade closed notification
    if (msg.type === 'trade_closed') {
      const key = `close_${msg.pair}_${msg.profit}`
      if (processedRef.current.has(key)) return
      processedRef.current.add(key)
      const profit = Number(msg.profit || 0)
      const emoji = profit >= 0 ? '+' : ''
      notify(
        `Trade ferme: ${msg.pair}`,
        `P&L: ${emoji}$${profit.toFixed(2)}`,
        `trade_${key}`,
      )
    }

    // Keep the set manageable
    if (processedRef.current.size > 200) {
      const entries = Array.from(processedRef.current)
      processedRef.current = new Set(entries.slice(-100))
    }
  }, [lastMessage, notify])
}
