/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';

interface AuthResponse {
  access_token: string;
  expires_in: number;
  token_type: 'Bearer';
}

interface ApiClientConfig {
  baseURL: string;
  username: string;
  password: string;
  authUrl: string;
}

export class ApiClient {
  private axiosInstance: AxiosInstance;
  private accessToken: string | null = null;
  private tokenExpirationTime: number | null = null;
  private readonly config: ApiClientConfig;

  constructor(config: ApiClientConfig) {
    this.config = config;
    this.axiosInstance = axios.create({
      baseURL: config.baseURL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add request interceptor to automatically add auth token
    this.axiosInstance.interceptors.request.use(
      async (config) => {
        // If we need to authenticate or refresh token
        if (this.shouldRefreshToken()) {
          await this.authenticate();
        }

        // Add the auth token to the request if we have one
        if (this.accessToken) {
          config.headers.Authorization = `Bearer ${this.accessToken}`;
        }

        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );
  }

  private shouldRefreshToken(): boolean {
    if (!this.accessToken || !this.tokenExpirationTime) {
      return true;
    }

    const bufferTimeMS = 14 * 60 * 1000;
    return Date.now() + bufferTimeMS >= this.tokenExpirationTime;
  }

  private async authenticate(): Promise<void> {
    try {

      const authData = new URLSearchParams();
      authData.append('username', this.config.username);
      authData.append('password', this.config.password);
      authData.append('grant_type', 'password');

      const authUrl = this.config.authUrl;

      const response = await axios.post<AuthResponse>(
        authUrl,
        authData,
        {
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
          }
        }
      );

      if (response.status === 400) {
        throw new Error(response.data as any);
      }

      this.accessToken = response.data.access_token;
      this.tokenExpirationTime = Date.now() + (response.data.expires_in * 1000);
    } catch (error: any) {
      if (axios.isAxiosError(error)) {
        console.error('Authentication failed:', error.message);
        if (error.response) {
            console.error('Response status:', error.response.status);
            console.error('Response data:', JSON.stringify(error.response.data, null, 2));
        }
      } else {
        console.error('Authentication failed:', error);
      }
      throw error;
    }
  }

  // Generic request method with automatic token handling
  async request<T>(config: AxiosRequestConfig): Promise<T> {
    try {
      const response = await this.axiosInstance.request<T>(config);
      return response.data;
    } catch (error) {
      // Handle specific error cases here
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 401) {
          // Token might be invalid, try to re-authenticate
          await this.authenticate();
          // Retry the request
          const response = await this.axiosInstance.request<T>(config);
          return response.data;
        }
      }
      throw error;
    }
  }

  // Convenience methods for common HTTP verbs
  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.request<T>({ ...config, method: 'GET', url });
  }

  async post<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return this.request<T>({ ...config, method: 'POST', url, data });
  }

  async put<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return this.request<T>({ ...config, method: 'PUT', url, data });
  }

  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.request<T>({ ...config, method: 'DELETE', url });
  }
}