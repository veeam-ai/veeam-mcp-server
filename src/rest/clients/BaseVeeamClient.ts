import { ApiClient } from '../ApiClient.js';
import { VeeamClient } from './VeeamClient.js';
import { ServiceInfo, AuthResult, ToolInvocationConfig } from '../../common/types.js';
import { ToolCallingError } from '../../common/errors.js';

export abstract class BaseVeeamClient implements VeeamClient {
    protected apiClient: ApiClient;

    constructor(baseURL: string, username: string, password: string, authUrl: string) {
        this.apiClient = new ApiClient({
            baseURL,
            username,
            password,
            authUrl
        });
    }

    abstract getServiceInfo(): Promise<ServiceInfo>;
    abstract authenticate(): Promise<AuthResult>;

    private isNotObject(value: unknown) {
        const invalidTypes = ['string', 'number', 'undefined', 'boolean', 'function'];
        
        return value === null || Number.isNaN(value) || invalidTypes.includes(typeof value);
    }
    
    private createQueryString(params: Record<string, unknown>): URLSearchParams {
        const queryParams = new URLSearchParams();
        const keys = Object.keys(params);
    
        keys.forEach((key) => {
            if (this.isNotObject(params[key])) {
                queryParams.append(key, String(params[key]));
            } else {
                queryParams.append(key, JSON.stringify(params[key]));
            }
        });
    
        return queryParams;
    }

    async getToolCallData(config: ToolInvocationConfig): Promise<{ data: unknown; status: string }> {
        const cfg = config;
        switch (config.tool_name) {
            case 'fetch_threat_center': {
                throw new ToolCallingError({
                    message: 'Fetching threat center is not implemented'
                });
            }
            case 'fetch_data_from_endpoint': {
                const query = this.createQueryString(config.parameters.query_params);
                let url = config.parameters.endpoint_path;

                if (query.size > 0) {
                    url = `${url}?${query.toString()}`;
                }

                try {
                    const response = await this.apiClient.get(url);
                    return { data: response, status: 'success' };
                } catch (err: any) {
                    if (err.response?.status === 404) {
                        throw new ToolCallingError({
                            message: `Failed to provide Veeam Intelligence response. URL ${config.parameters.endpoint_path} does not exist`
                        });
                    }

                    throw new ToolCallingError(err.response?.data || {
                        message: `Failed to fetch data from endpoint: ${err.message || 'Unknown error'}`
                    });
                }
            }
            default: {
                throw new ToolCallingError({
                    message: `Failed to provide Veeam Intelligence response. Unable to load ${cfg.tool_name}`
                });
            }
        }
    }
}
