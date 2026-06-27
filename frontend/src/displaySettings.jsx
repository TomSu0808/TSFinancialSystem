import { createContext, useContext } from 'react'

export const DisplaySettingsContext = createContext({
  displayCurrency: 'USD',
  setDisplayCurrency: () => {},
})

export function useDisplaySettings() {
  return useContext(DisplaySettingsContext)
}

// Convert amount from sourceCurrency to displayCurrency using USD/CNY rate.
// rate: how many CNY per 1 USD (e.g. 7.25).
// Returns null if conversion requires rate but rate is unavailable.
export function convertAmount(amount, sourceCurrency, displayCurrency, rate) {
  if (amount == null) return null
  if (sourceCurrency === displayCurrency) return amount

  // Step 1: source → CNY
  let cny
  if (sourceCurrency === 'CNY') {
    cny = amount
  } else if (sourceCurrency === 'USD') {
    if (!rate) return null
    cny = amount * rate
  } else if (sourceCurrency === 'HKD') {
    if (!rate) return null
    // HKD pegged ~7.8 per USD; rate is CNY per USD
    cny = amount * (rate / 7.8)
  } else {
    cny = amount // unknown currency, treat as CNY
  }

  // Step 2: CNY → displayCurrency
  if (displayCurrency === 'CNY') return cny
  if (displayCurrency === 'USD') {
    if (!rate) return null
    return cny / rate
  }
  return cny
}
