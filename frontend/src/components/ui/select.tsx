import { useEffect, useState } from 'react'
import {
  Listbox,
  ListboxButton,
  ListboxOption,
  ListboxOptions,
} from '@headlessui/react'
import { Check, ChevronDown } from 'lucide-react'
import clsx from 'clsx'

// Polyfill ResizeObserver for jsdom test environments if missing
if (typeof window !== 'undefined' && !window.ResizeObserver) {
  window.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

export interface SelectProps {
  id?: string
  name?: string
  label?: string
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  disabled?: boolean
  className?: string
  placeholder?: string
  required?: boolean
  'aria-label'?: string
}

export function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.innerWidth < breakpoint
  })

  useEffect(() => {
    if (typeof window === 'undefined') return

    const update = () => {
      if (typeof window.matchMedia === 'function') {
        const mql = window.matchMedia(`(max-width: ${breakpoint - 1}px)`)
        setIsMobile(mql.matches)
      } else {
        setIsMobile(window.innerWidth < breakpoint)
      }
    }

    update()

    if (typeof window.matchMedia === 'function') {
      const mql = window.matchMedia(`(max-width: ${breakpoint - 1}px)`)
      mql.addEventListener('change', update)
      window.addEventListener('resize', update)
      return () => {
        mql.removeEventListener('change', update)
        window.removeEventListener('resize', update)
      }
    } else {
      window.addEventListener('resize', update)
      return () => window.removeEventListener('resize', update)
    }
  }, [breakpoint])

  return isMobile
}

export function Select({
  id,
  name,
  label,
  value,
  options,
  onChange,
  disabled = false,
  className = '',
  placeholder = 'Select an option',
  required = false,
  'aria-label': ariaLabel,
}: SelectProps) {
  const isMobile = useIsMobile()
  const effectiveLabel = label || ariaLabel || placeholder
  const selectedOption = options.find((opt) => opt.value === value)

  // On mobile (< md / 768px), keep the native <select> for mobile OS wheel/sheet pickers
  if (isMobile) {
    return (
      <div className={clsx('relative w-full', className)}>
        <select
          id={id}
          name={name}
          aria-label={effectiveLabel}
          value={value}
          disabled={disabled}
          required={required}
          onChange={(e) => onChange(e.target.value)}
          className={clsx(
            'h-10 w-full rounded-input border border-border bg-card px-3 text-sm text-foreground outline-none transition',
            'focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 disabled:cursor-not-allowed disabled:opacity-60',
          )}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} disabled={opt.disabled}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    )
  }

  // On desktop (>= md), render the accessible custom Headless UI Listbox
  return (
    <Listbox
      value={value}
      onChange={onChange}
      disabled={disabled}
      {...(name !== undefined ? { name } : {})}
    >
      {({ open }) => (
        <div className={clsx('relative w-full', className)}>
          <ListboxButton
            id={id}
            aria-label={effectiveLabel}
            disabled={disabled}
            className={clsx(
              'flex h-10 w-full items-center justify-between rounded-input border border-border bg-card px-3.5 text-left text-sm text-foreground outline-none transition',
              'focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20',
              'disabled:cursor-not-allowed disabled:opacity-60',
              open && 'border-brand-500 ring-2 ring-brand-500/20',
            )}
          >
            <span className="truncate">
              {selectedOption ? selectedOption.label : placeholder}
            </span>
            <ChevronDown
              className={clsx(
                'ml-2 h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200',
                open && 'rotate-180 text-brand-500',
              )}
            />
          </ListboxButton>

          <ListboxOptions
            className={clsx(
              'shadow-dropdown absolute left-0 top-[calc(100%+6px)] z-50',
              'min-w-full w-max max-w-[min(100vw-2rem,36rem)] max-h-60 overflow-y-auto',
              'rounded-card border border-border bg-card p-1 text-foreground outline-none',
            )}
          >
            {options.map((opt) => (
              <ListboxOption
                key={opt.value}
                value={opt.value}
                disabled={Boolean(opt.disabled)}
                className={({ focus, selected }) =>
                  clsx(
                    'relative flex cursor-pointer select-none items-center justify-between gap-3 rounded-md px-3 py-2 text-sm outline-none transition-colors',
                    'whitespace-normal break-words sm:whitespace-nowrap',
                    opt.disabled && 'cursor-not-allowed opacity-50',
                    selected
                      ? 'bg-brand-100 font-medium text-brand-900 dark:bg-amber-950/60 dark:text-amber-200'
                      : focus
                        ? 'bg-secondary text-secondary-foreground'
                        : 'text-foreground hover:bg-secondary',
                  )
                }
              >
                {({ selected }) => (
                  <>
                    <span className="truncate sm:overflow-visible">
                      {opt.label}
                    </span>
                    {selected ? (
                      <Check className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-400" />
                    ) : (
                      <span className="h-4 w-4 shrink-0" />
                    )}
                  </>
                )}
              </ListboxOption>
            ))}
          </ListboxOptions>
        </div>
      )}
    </Listbox>
  )
}

export default Select
