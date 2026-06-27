import { createContext, useContext } from 'react'

// 'cn' = 红涨绿跌（A股惯例）  'us' = 绿涨红跌（欧美惯例）
export const ColorSchemeContext = createContext('cn')

export function useColorScheme() {
  const scheme = useContext(ColorSchemeContext)
  return {
    upColor:   scheme === 'cn' ? '#cf1322' : '#3f8600',
    downColor: scheme === 'cn' ? '#3f8600' : '#cf1322',
  }
}
