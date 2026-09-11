import type { Indicator } from "./schema.js";

/** Simple moving average, updated incrementally so a full backtest doesn't
 * re-sum the whole window on every candle. */
export class SmaIndicator {
  private window: number[] = [];
  private sum = 0;

  constructor(private readonly period: number) {}

  /** Feed the next close and return the current SMA, or `undefined` while
   * the window hasn't filled yet. */
  update(value: number): number | undefined {
    this.window.push(value);
    this.sum += value;
    if (this.window.length > this.period) {
      this.sum -= this.window.shift() as number;
    }
    if (this.window.length < this.period) {
      return undefined;
    }
    return this.sum / this.period;
  }
}

export function createIndicator(spec: Indicator): SmaIndicator {
  switch (spec.type) {
    case "sma":
      return new SmaIndicator(spec.period);
  }
}

/** Tracks every indicator in a strategy and exposes the current and prior
 * value of each, which is exactly what crossover rules need. */
export class IndicatorSet {
  private readonly instances = new Map<string, SmaIndicator>();
  private previous = new Map<string, number>();
  private current = new Map<string, number>();

  constructor(specs: Indicator[]) {
    for (const spec of specs) {
      this.instances.set(spec.id, createIndicator(spec));
    }
  }

  update(close: number): void {
    this.previous = this.current;
    this.current = new Map();
    for (const [id, indicator] of this.instances) {
      const value = indicator.update(close);
      if (value !== undefined) {
        this.current.set(id, value);
      }
    }
  }

  currentValue(id: string): number | undefined {
    return this.current.get(id);
  }

  previousValue(id: string): number | undefined {
    return this.previous.get(id);
  }
}

export function crossesAbove(
  prevLeft: number | undefined,
  prevRight: number | undefined,
  curLeft: number | undefined,
  curRight: number | undefined,
): boolean {
  if (
    prevLeft === undefined ||
    prevRight === undefined ||
    curLeft === undefined ||
    curRight === undefined
  ) {
    return false;
  }
  return prevLeft <= prevRight && curLeft > curRight;
}

export function crossesBelow(
  prevLeft: number | undefined,
  prevRight: number | undefined,
  curLeft: number | undefined,
  curRight: number | undefined,
): boolean {
  if (
    prevLeft === undefined ||
    prevRight === undefined ||
    curLeft === undefined ||
    curRight === undefined
  ) {
    return false;
  }
  return prevLeft >= prevRight && curLeft < curRight;
}
