import * as React from "react";

/**
 * The shadcn/ui components are written for React 19, where `ref` is an ordinary prop. On React 18
 * (standards/07) a function component drops refs, which breaks `asChild` triggers, Radix presence
 * animations and react-hook-form focus. `fwd` wraps a component in `forwardRef` while keeping the
 * component's props type (which already includes `ref` for DOM and Radix elements).
 */
export function fwd<P extends object>(
  render: (props: P, ref: React.ForwardedRef<unknown>) => React.ReactNode,
): (props: P) => React.ReactNode {
  const component = React.forwardRef(
    render as unknown as React.ForwardRefRenderFunction<unknown, React.PropsWithoutRef<P>>,
  );
  component.displayName = render.name;
  return component as unknown as (props: P) => React.ReactNode;
}
