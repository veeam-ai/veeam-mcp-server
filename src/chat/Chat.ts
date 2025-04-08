import { Socket } from '../socket/Socket.js';
import { MessageRole, ServiceInfo, AuthResponse } from '../common/types.js';
import { SocketEmitConfig } from '../socket/types.js';
import { ChatInterface } from './types.js';
import { QuestionAnswerHandler } from './QuestionAnswerHandler.js';
import { VeeamApiClient } from '../rest/VeeamApiClient.js';
import { debug } from '../common/debug.js';

export class Chat implements ChatInterface {
    private socket: Socket;
    private serviceInfo: ServiceInfo;
    private authResponse: AuthResponse;
    private api: VeeamApiClient;

    constructor(authResponse: AuthResponse, serviceInfo: ServiceInfo) {
        this.serviceInfo = serviceInfo;
        this.authResponse = authResponse;
        this.socket = new Socket();
        this.api = new VeeamApiClient();
        this.initializeSocket();
    }

    private initializeSocket() {
        this.socket.initSocket(this.serviceInfo, {
            productSuffix: '',
            socketPath: '/socket.io',
            withCredentials: true,
        });
        this.socket.setAuthToken(this.authResponse.access_token);
        this.socket.connect();
    }

    public async answer(message: string): Promise<string> {
        // Connect socket
        // Attach Response Sink
        // Send question
        // Await response in sink (string message + list[artifact])
        // Return message
        
        const config: SocketEmitConfig = {
            name: 'chat',
            value: {
                messages: [
                    {
                        role: MessageRole.user,
                        content: message,
                    },
                ],
                artifacts: [],
                metadata: {
                    pii_data_in_history: false,
                },
            }
        };

        const handler = new QuestionAnswerHandler(this.socket, this.serviceInfo, this.api);

        this.socket.subscribe(handler);
        this.socket.emit(config);

        await handler.getMessageCompletePromise();
        const answer = handler.getMessage();
        const artifacts = handler.getArtifacts();

        //debug();
        return answer;
    }

    public reset(): void {
        // Mock implementation
        // This would typically clear the chat history and reset the socket connection
        this.socket.disconnect();
        this.initializeSocket();
    }

    public disconnect(): void {
        this.socket.disconnect();
    }
} 