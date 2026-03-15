import { useState, useCallback } from 'react'
import translations, { Lang } from './translations'

export function useTranslation() {
  const [lang, setLang] = useState<Lang>(() => {
    return (localStorage.getItem('lang') as Lang) || 'fr'
  })

  const t = useCallback((key: string): string => {
    return translations[lang]?.[key] || translations['fr']?.[key] || key
  }, [lang])

  const switchLang = useCallback(() => {
    setLang(prev => {
      const next = prev === 'fr' ? 'en' : 'fr'
      localStorage.setItem('lang', next)
      return next
    })
  }, [])

  return { t, lang, switchLang }
}
