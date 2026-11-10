import * as React from 'react'
import { cn } from '../../lib/utils'

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'secondary' | 'destructive' | 'outline' | 'amber' | 'emerald' | 'rose'
}

function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  const variantStyles = {
    default:
      'border-transparent bg-amber-500 text-slate-950 font-semibold',
    secondary:
      'border-transparent bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-100',
    destructive:
      'border-transparent bg-rose-500 text-white dark:bg-rose-900 dark:text-rose-200',
    outline:
      'text-slate-950 dark:text-slate-50 border-slate-200 dark:border-slate-800',
    amber:
      'border-amber-300 bg-amber-100 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/50 dark:text-amber-300',
    emerald:
      'border-emerald-300 bg-emerald-100 text-emerald-900 dark:border-emerald-700/60 dark:bg-emerald-950/50 dark:text-emerald-300',
    rose:
      'border-rose-300 bg-rose-100 text-rose-900 dark:border-rose-700/60 dark:bg-rose-950/50 dark:text-rose-300',
  }[variant]

  return (
    <div
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2',
        variantStyles,
        className
      )}
      {...props}
    />
  )
}

export { Badge }
