export function debug(): void {
    if (process.env.NODE_ENV === 'development') {
        debugger;
    }
} 