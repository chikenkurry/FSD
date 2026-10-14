import type { Form } from '@/types/form';

// Point this to your Golang backend URL
const API_BASE_URL = 'http://localhost:8080/v1';

export const apiService = {
  /**
   * Fetch all forms from the Go backend (for Frame 3 dashboard)
   */
  async getForms(userID: string): Promise<Form[]> {
    try {
      const encodedUserID = encodeURIComponent(userID)
      const response = await fetch(`${API_BASE_URL}/users/${encodedUserID}`);
      if (!response.ok) {
        throw new Error('Failed to fetch forms from server');
      }
      return await response.json();
    } catch (error) {
      console.error('API Error (getForms):', error);
      throw error;
    }
  },

  /**
   * Send a new form payload to the Go backend (from Frame 4 form creator)
   */
  async createForm(formData: Form): Promise<any> {
    try {
      const response = await fetch(`${API_BASE_URL}/forms`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        throw new Error('Failed to save form to server');
      }
      return await response.json();
    } catch (error) {
      console.error('API Error (createForm):', error);
      throw error;
    }
  },

  async fakeLogin(username: string): Promise<any> {
    try {
      const encodedUsername = encodeURIComponent(username)
      const response = await fetch(`${API_BASE_URL}/usersbyname/${encodedUsername}`);
      if (!response.ok) {
        throw new Error('Failed to fetch user from server')
      }
      return await response.json();
    } catch (error) {
      console.error('API Error (fakeLogin):', error);
      throw error;
    }
  },
};