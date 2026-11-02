// Delayed execution responses may finish after the reader has navigated away.
// Keep the underlying job intact while applying navigation/errors only to the
// page where the action began, including leave-and-return navigation.
export class PageActions {
  private revision = 0;
  private readAddress: () => string;
  constructor(readAddress = () => location.hash) { this.readAddress = readAddress; }
  moved() { this.revision++; }
  async run<T>(action: () => Promise<T>, apply: (value: T) => void): Promise<void> {
    const revision = this.revision, address = this.readAddress();
    const current = () => revision === this.revision && address === this.readAddress();
    try {
      const result = await action();
      if (current()) apply(result);
    } catch (error) { if (current()) throw error; }
  }
}
