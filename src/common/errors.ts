export class ToolCallingError extends Error {
    public data: unknown;

    constructor(data: unknown) {
        super();
        this.name = 'ToolCallingError';
        this.data = data;
    }
}
