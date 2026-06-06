# Template: React Application

React frontend application development. Covers component patterns, state management, architecture, UX, and testing.

## Architecture

```
pages/         -> Route-level components
components/    -> Reusable UI components
hooks/         -> Custom hooks (shared logic)
services/      -> API calls, external integrations
stores/        -> State management
```

### Data Flow

- Props down, events up
- Avoid prop drilling (use context or composition)
- Container/presentational split where helpful

## Components

- Functional components with hooks
- Composition over inheritance
- Single responsibility per component
- Props for configuration, hooks for behavior
- Organize by feature/domain, not by type
- Colocate component + test + styles + hooks
- Extract shared components to `components/common/`
- Keep component files under 200 lines

### Error Boundaries

```tsx
class ErrorBoundary extends React.Component<Props, { hasError: boolean }> {
  static getDerivedStateFromError() { return { hasError: true } }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    logError(error, info)
  }
  render() {
    if (this.state.hasError) return this.props.fallback
    return this.props.children
  }
}
```

Wrap route-level and feature-level boundaries. Never wrap individual components.

## State Management

- **Local state**: `useState` for component-scoped state
- **Shared state**: Context for low-frequency updates (theme, auth, locale)
- **Server state**: TanStack Query or SWR for API data (not Redux)
- **Complex state**: `useReducer` for multi-field forms or state machines
- Avoid prop drilling beyond 2 levels — use Context or composition
- Single source of truth for app state
- Immutable state updates
- Derived state computed, not stored
- Optimistic updates with rollback

## Forms

- Controlled components for simple forms
- React Hook Form or Formik for complex forms
- Validate on submit, show errors on blur
- Disable submit button during async operations
- Client-side validation for UX, server-side for security
- Clear error messages near inputs
- Preserve user input on errors

## Custom Hooks

```typescript
export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay)
    return () => clearTimeout(handler)
  }, [value, delay])
  return debouncedValue
}
```

- Extract reusable logic into `use*` hooks
- Keep hooks focused — one concern per hook
- Always specify complete dependency arrays

## Performance

- `useMemo` for expensive computations
- `useCallback` for stable function references passed to children
- `React.memo` for pure component optimization
- List virtualization for large datasets (react-window, react-virtuoso)
- Lazy loading with `React.lazy` + `Suspense`
- Avoid inline object/array literals in JSX props
- Avoid unnecessary re-renders
- Monitor bundle size
- Debounce/throttle for frequent events

## UX

- [ ] Loading states for async operations
- [ ] Error states with recovery actions
- [ ] Responsive design (mobile/desktop)
- [ ] No layout shifts on load
- [ ] Keyboard navigation support
- [ ] Focus management

## Accessibility

- [ ] Semantic HTML elements
- [ ] ARIA labels where needed
- [ ] Color contrast ratios (WCAG AA minimum)
- [ ] Screen reader testing

## Testing

- React Testing Library over Enzyme
- Test behavior, not implementation
- Mock external dependencies
- Use `screen` queries over container queries
- Test user interactions (click, type, submit) not internal state

## Checklist

- [ ] Components under 200 lines
- [ ] No prop drilling beyond 2 levels
- [ ] Server state via TanStack Query/SWR
- [ ] Error boundaries at route/feature level
- [ ] Loading and error states on all async UI
- [ ] Keyboard navigation works
- [ ] WCAG AA contrast ratios
- [ ] Tests cover user interactions
