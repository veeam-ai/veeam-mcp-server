import { SocketMessageData, SocketSubscribeHandlers, ResponseChunk } from '../socket/types.js';
import { Artifact, ServiceInfo, ChatbotMode, ToolInvocationConfig } from '../common/types.js';
import { Socket } from '../socket/Socket.js';
import { VeeamApiClient } from '../rest/VeeamApiClient.js';
import { ToolCallingError } from '../common/errors.js';
import { debug } from '../common/debug.js';

export class QuestionAnswerHandler implements SocketSubscribeHandlers {
    private message: string = '';
    private artifacts: Artifact[] = [];
    private messageCompletePromise: Promise<void>;
    private resolveMessageComplete: (() => void) | null = null;
    private socket: Socket;
    private serviceInfo: ServiceInfo;
    private api: VeeamApiClient;

    constructor(socket: Socket, serviceInfo: ServiceInfo, api: VeeamApiClient) {
        this.socket = socket;
        this.serviceInfo = serviceInfo;
        this.api = api;
        this.messageCompletePromise = new Promise((resolve) => {
            this.resolveMessageComplete = resolve;
        });
    }

    private convertDataframeToMarkdownTable(data: any): string {
        const { columns, data: rows } = data;
        
        // Create header row
        const header = `| ${columns.join(' | ')} |\n`;
        
        // Create separator row
        const separator = `| ${columns.map(() => '---').join(' | ')} |\n`;
        
        // Create data rows with object handling
        const dataRows = rows.map((row: any[]) => {
            const processedRow = row.map((cell: any) => {
                if (typeof cell === 'object' && cell !== null) {
                    try {
                        // Try to stringify as JSON if it's a valid JSON object
                        return JSON.stringify(cell);
                    } catch {
                        // If not valid JSON, convert to string
                        return String(cell);
                    }
                }
                return cell;
            });
            return `| ${processedRow.join(' | ')} |`;
        }).join('\n');
        
        return `\n${header}${separator}${dataRows}\n`;
    }

    // Socket io handlers
    public async onChunk(data: SocketMessageData): Promise<void> {
        const chunk = JSON.parse(data.message) as ResponseChunk;
        
        if (chunk.type === 'token') {
            this.message += chunk.payload;
        } else if (chunk.type === 'artifact') {
            this.artifacts.push(chunk.payload);
            
            // If it's a dataframe artifact, convert it to markdown table and append to message
            if (chunk.payload.type === 'dataframe') {
                const markdownTable = this.convertDataframeToMarkdownTable(chunk.payload.data);
                this.message += markdownTable;
            }
        }
    }

    public async onConnected(data: SocketMessageData): Promise<void> {
        //debug();
    }

    public async onConnectionError(data: SocketMessageData): Promise<void> {
        debug();
    }

    public async onConnectionInfoError(data: SocketMessageData): Promise<void> {
        debug();
    }

    public async onDisconnected(data: SocketMessageData): Promise<void> {
        if (this.resolveMessageComplete) {
            this.resolveMessageComplete();
            this.resolveMessageComplete = null;
        }
    }

    public async onReconnectError(data: SocketMessageData): Promise<void> {
        debug();
    }

    public async onReconnectFailed(data: SocketMessageData): Promise<void> {
        debug();
    }

    public async onResponseError(data: SocketMessageData): Promise<void> {
        debug();
    }

    public async onTokenInvalid(data: SocketMessageData): Promise<void> {
        debug();
    }

    public async onTokenRequired(data: SocketMessageData): Promise<void> {
        // TODO: Authenticate and set token 
        debug();
    }

    public async onToolInvocation(data: SocketMessageData): Promise<void> {
        /*
            {
                "invocation_id":"ba3e5302-8417-45e9-a1af-c62664067adf",
                "tool_name":"fetch_data_from_endpoint",
                "parameters":{
                    "endpoint_path":"/api/v2.2/alarms/triggeredAlarms",
                    "query_params":{
                        "Offset":0,
                        "Limit":1000,
                        "Filter":{
                            "property":"status",
                            "operation":"in",
                            "collation":"ignorecase",
                            "value":[
                            "Error",
                            "Warning"
                            ]
                        },
                        "Sort":{
                            "property":"triggeredTime",
                            "direction":"descending",
                            "collation":"ignorecase"
                        },
                        "Select":"name,triggeredTime,repeatCount,status,alarmAssignment"
                    }
                }
            }

            Offset=0&Limit=20&Filter=%7B%22property%22%3A%22status%22%2C%22operation%22%3A%22in%22%2C%22collation%22%3A%22ignorecase%22%2C%22value%22%3A%5B%22Error%22%2C%22Warning%22%5D%7D&Sort=%7B%22property%22%3A%22triggeredTime%22%2C%22direction%22%3A%22descending%22%2C%22collation%22%3A%22ignorecase%22%7D&Select=name%2CtriggeredTime%2Cstatus%2CalarmAssignment
        */

        const mode = this.serviceInfo.chatbotMode;
        const config = JSON.parse(data.message) as ToolInvocationConfig;

        if (this.serviceInfo.chatbotMode === ChatbotMode.Base) {
            this.socket.emit({
                name: 'tool_result',
                value: {
                    invocation_id: config.invocation_id,
                    status: 'error',
                    data: 'Chatbot running in "Base" mode. Tool calls are restricted in this mode',
                },
            });
            return;
        }

        try {
            const { data, status } = await this.api.getToolCallData(config);

            this.socket.emit({
                name: 'tool_result',
                value: {
                    invocation_id: config.invocation_id,
                    status,
                    data,
                },
            });
        } catch (err) {
            const error = err as ToolCallingError;

            this.socket.emit({
                name: 'tool_result',
                value: {
                    invocation_id: config.invocation_id,
                    status: 'error',
                    data: error.data,
                },
            });
        }
    }

    public async onUnknownProduct(data: SocketMessageData): Promise<void> {
        debug();
    }

    public async onProcessUpdate(data: SocketMessageData): Promise<void> {
        debug();
    }

    public async onProcessStart(data: SocketMessageData): Promise<void> {
        debug();
    }

    public async onProcessEnd(data: SocketMessageData): Promise<void> {
        debug();
    }

    public getMessageCompletePromise(): Promise<void> {
        return this.messageCompletePromise;
    }

    public getMessage(): string {
        return this.message;
    }

    public getArtifacts(): Artifact[] {
        return this.artifacts;
    }
}