import React, { useEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'

export interface SelectOption {
  value: string
  label: string
}

interface CustomSelectProps {
  id?: string
  label: string
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  disabled?: boolean
  className?: string
}

export function CustomSelect({
  id,
  label,
  value,
  options,
  onChange,
  disabled = false,
  className = '',
}: CustomSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const selectedOption = options.find((opt) => opt.value === value) || options[0]

  // Close when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent | TouchEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      document.addEventListener('touchstart', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('touchstart', handleClickOutside)
    }
  }, [isOpen])

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return

    if (e.key === 'Escape') {
      setIsOpen(false)
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      setIsOpen((prev) => !prev)
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!isOpen) {
        setIsOpen(true)
      } else {
        const currentIndex = options.findIndex((opt) => opt.value === value)
        const nextIndex = (currentIndex + 1) % options.length
        const nextOption = options[nextIndex]
        if (nextOption) {
          onChange(nextOption.value)
        }
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (!isOpen) {
        setIsOpen(true)
      } else {
        const currentIndex = options.findIndex((opt) => opt.value === value)
        const prevIndex = (currentIndex - 1 + options.length) % options.length
        const prevOption = options[prevIndex]
        if (prevOption) {
          onChange(prevOption.value)
        }
      }
    }
  }

  const handleSelect = (optionValue: string) => {
    onChange(optionValue)
    setIsOpen(false)
  }

  return (
    <div ref={containerRef} className={`relative w-full ${className}`}>
      {/* Hidden native select for form synchronization and test runner compatibility */}
      <select
        id={id}
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="sr-only"
        tabIndex={-1}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* 1. Trigger button: app-select-trigger, Custom chevron icon */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((prev) => !prev)}
        onKeyDown={handleKeyDown}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        className={`app-select-trigger ${
          isOpen
            ? 'border-brand-500 ring-2 ring-brand-500/20'
            : 'hover:border-slate-300 dark:hover:border-slate-600'
        }`}
      >
        <span className="truncate font-normal">
          {selectedOption ? selectedOption.label : 'Select an option'}
        </span>
        <ChevronDown
          className={`h-4 w-4 text-slate-500 transition-transform duration-200 dark:text-slate-400 ${
            isOpen ? 'rotate-180 text-brand-500' : ''
          }`}
        />
      </button>

      {/* 2. Options container (dropdown list): Position: absolute, z-index 50, top full + 6px offset */}
      {isOpen && (
        <ul
          role="listbox"
          aria-label={label}
          className="shadow-dropdown absolute left-0 right-0 top-[calc(100%+6px)] z-50 overflow-hidden rounded-card border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
        >
          {options.map((opt) => {
            const isSelected = opt.value === value
            return (
              <li
                key={opt.value}
                role="option"
                aria-selected={isSelected}
                onClick={() => handleSelect(opt.value)}
                className={`cursor-pointer px-4 py-2.5 text-sm transition-colors ${
                  isSelected
                    ? 'bg-brand-500 font-medium text-white'
                    : 'text-slate-900 hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-800'
                }`}
              >
                {opt.label}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
