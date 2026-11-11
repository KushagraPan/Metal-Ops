import * as React from 'react'
import { cn } from '../../lib/utils'

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'secondary' | 'destructive' | 'outline' | 'amber' | 'emerald' | 'rose'
}

function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  const variantStyles = {
    default:
      'border-transparent bg-primary text-primary-foreground font-semibold',
    secondary:
      'border-transparent bg-secondary text-secondary-foreground',
    destructive:
      'border-transparent bg-destructive text-destructive-foreground',
    outline:
      'text-foreground border-border',
    amber:
      'border-amber-500/30 bg-amber-500/15 text-amber-700 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-300 font-semibold',
    emerald:
      'border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-300 font-semibold',
    rose:
      'border-rose-500/30 bg-rose-500/15 text-rose-700 dark:border-rose-400/30 dark:bg-rose-400/10 dark:text-rose-300 font-semibold',
  }[variant]

  return (
    <div
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
        variantStyles,
        className
      )}
      {...props}
    />
  )
}

export { Badge }
