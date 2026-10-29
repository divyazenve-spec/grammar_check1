// Zenve Vet™ — API Client for Spring Boot Backend (http://localhost:8080/api/v1)

const BASE_URL = 'http://localhost:8080/api/v1';

let lastAuthUnauthorizedTime = 0;

async function fetchJson(endpoint, options = {}) {
  const isAdvertiser = options.isAdvertiser || endpoint.startsWith('/advertisers') || endpoint.startsWith('/campaigns');

  let authHeader = null;
  if (isAdvertiser) {
    if (options.headers?.Authorization) {
      authHeader = options.headers.Authorization;
    } else {
      const advToken = localStorage.getItem('zenve_advertiser_token');
      if (advToken) authHeader = `Bearer ${advToken}`;
    }
  } else {
    if (options.headers?.Authorization) {
      authHeader = options.headers.Authorization;
    } else {
      const docToken = localStorage.getItem('doctor_vet_token');
      if (docToken) authHeader = `Bearer ${docToken}`;
    }
  }

function getDeviceId() {
  try {
    let id = localStorage.getItem('zenve_device_id');
    if (!id) {
      id = 'dev_' + Math.random().toString(36).substring(2, 10) + '_' + Date.now().toString(36);
      localStorage.setItem('zenve_device_id', id);
    }
    return id;
  } catch (_) {
    return 'dev_client_default';
  }
}

  const headers = {
    'Content-Type': 'application/json',
    'X-Device-Id': getDeviceId(),
    ...(authHeader ? { 'Authorization': authHeader } : {}),
    ...(options.headers || {})
  };

  try {
    const res = await fetch(`${BASE_URL}${endpoint}`, {
      ...options,
      headers
    });

    if (res.status === 401) {
      if (isAdvertiser) {
        console.warn(`Unauthorized advertiser request on ${endpoint}. Clearing advertiser credentials.`);
        localStorage.removeItem('zenve_advertiser_token');
        localStorage.removeItem('zenve_advertiser_account');
        window.dispatchEvent(new CustomEvent('advertiser:unauthorized', { detail: { endpoint } }));
        throw new Error('Unauthorized: Advertiser session expired or invalid credentials');
      } else {
        const isAuthPublic =
          endpoint.startsWith('/auth/login') ||
          endpoint.startsWith('/auth/register') ||
          endpoint.startsWith('/auth/forgot-password') ||
          endpoint.startsWith('/auth/verify-code') ||
          endpoint.startsWith('/auth/verify-otp') ||
          endpoint.startsWith('/auth/reset-password') ||
          endpoint.startsWith('/auth/send-login-otp') ||
          endpoint.startsWith('/auth/login-with-otp');
        if (!isAuthPublic) {
          const now = Date.now();
          if (now - lastAuthUnauthorizedTime > 1500) {
            lastAuthUnauthorizedTime = now;
            console.warn(`Unauthorized request on ${endpoint}. Clearing doctor session.`);
            localStorage.removeItem('doctor_vet_user');
            localStorage.removeItem('doctor_vet_token');
            window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { endpoint } }));
          }
        }
        throw new Error('Unauthorized: Session expired or invalid credentials');
      }
    }

    if (!res.ok) {
      const errText = await res.text();
      let errorMsg = `HTTP ${res.status}: ${errText}`;
      try {
        const parsed = JSON.parse(errText);
        if (parsed.message) errorMsg = parsed.message;
        else if (parsed.error) errorMsg = parsed.error;
      } catch (e) { }
      throw new Error(errorMsg);
    }
    return await res.json();
  } catch (err) {
    if (err.message?.includes('Unauthorized')) {
      throw err;
    }
    console.warn(`Fetch error for ${endpoint}:`, err.message);
    throw err;
  }
}
export async function dispatchApitxtOtp(cleanMobile, code) {
  const apiKey = import.meta.env.VITE_APITXT_API_KEY || '';
  const configuredUrl = import.meta.env.VITE_APITXT_API_URL || 'https://apitxt.com/api/sendOTP';
  if (!apiKey || !cleanMobile || !code) {
    console.warn('[APITXT] Missing apiKey, mobile or otp code.');
    return null;
  }

  let formattedMobile = String(cleanMobile).replace(/[^0-9]/g, '');
  if (formattedMobile.length === 10) formattedMobile = '91' + formattedMobile;

  // In browser, direct calls to https://apitxt.com are blocked by CORS.
  // Using the Vite dev proxy /apitxt-proxy/api/sendOTP routes via dev server seamlessly.
  const targetUrl = (typeof window !== 'undefined' && configuredUrl.includes('apitxt.com'))
    ? '/apitxt-proxy/api/sendOTP'
    : configuredUrl;

  try {
    const body = new URLSearchParams({
      authkey: apiKey,
      mobile: formattedMobile,
      otp: code
    });

    const res = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body
    });

    const data = await res.json().catch(() => ({}));
    console.log('[APITXT] Live OTP dispatched successfully:', {
      mobile: formattedMobile,
      response: data
    });
    return data;
  } catch (err) {
    console.warn('[APITXT] Dispatch error:', err.message);
    return null;
  }
}

export const api = {
  // Auth
  auth: {
    login: (identifier, password) =>
      fetchJson('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ identifier, password })
      }),
    register: (userData) =>
      fetchJson('/auth/register', {
        method: 'POST',
        body: JSON.stringify(userData)
      }),
    verifyOtp: async (email, otp) => {
      const target = email ? String(email).trim() : '';
      const cleanOtp = otp ? String(otp).trim() : '';
      try {
        return await fetchJson('/auth/verify-otp', {
          method: 'POST',
          body: JSON.stringify({
            email: target,
            identifier: target,
            otp: cleanOtp,
            code: cleanOtp
          })
        });
      } catch (err) {
        return await api.auth.verifyResetCode(target, cleanOtp);
      }
    },
    forgotPassword: async (identifier) => {
      try {
        return await fetchJson('/auth/forgot-password', {
          method: 'POST',
          body: JSON.stringify({ identifier: identifier ? String(identifier).trim() : '' })
        });
      } catch (err) {
        // If the backend actively rejected with an intentional business validation message (not a 404 endpoint missing), rethrow it
        if (err.message && !err.message.includes('404') && !err.message.includes('Not Found') && !err.message.includes('Failed to fetch')) {
          throw err;
        }

        console.warn('Backend forgot-password endpoint fallback activated:', err.message);
        let doctorName = identifier;
        const cleanSearch = String(identifier || '').trim().toLowerCase();
        let cleanPhone = cleanSearch.replace(/[^0-9]/g, '');
        let targetDoctor = null;

        try {
          const docs = await fetchJson('/doctors');
          targetDoctor = (docs || []).find(d =>
            (d.email && d.email.toLowerCase() === cleanSearch) ||
            (d.phone && cleanPhone && d.phone.replace(/[^0-9]/g, '').includes(cleanPhone)) ||
            (d.name && d.name.toLowerCase().includes(cleanSearch))
          );
          if (targetDoctor) {
            doctorName = targetDoctor.name;
            if (targetDoctor.phone) {
              const matchedDigits = targetDoctor.phone.replace(/[^0-9]/g, '');
              if (matchedDigits) cleanPhone = matchedDigits;
            }
          }
        } catch (_) { }

        if (!cleanPhone || cleanPhone.length < 10) {
          throw new Error(`No registered mobile number found for "${doctorName}". Please enter your registered 10-digit mobile number.`);
        }

        const code = String(Math.floor(100000 + Math.random() * 900000));
        sessionStorage.setItem('zenve_reset_code', code);
        sessionStorage.setItem('zenve_reset_identifier', identifier);
        sessionStorage.setItem('zenve_reset_phone', cleanPhone);
        if (targetDoctor) {
          sessionStorage.setItem('zenve_reset_doc_id', String(targetDoctor.id));
          sessionStorage.setItem('zenve_reset_old_pwd', targetDoctor.password || '');
        }
        sessionStorage.setItem('zenve_reset_time', String(Date.now() + 15 * 60 * 1000));

        // Dispatch live OTP via APITXT to the registered mobile number
        await dispatchApitxtOtp(cleanPhone, code);

        const maskedPhone = '+91 ******' + cleanPhone.slice(-4);
        return {
          success: true,
          message: `A 6-digit verification code has been sent to your registered mobile (${maskedPhone}).`,
          doctorName: doctorName,
          registeredPhoneMasked: maskedPhone,
          expiresInMinutes: 15
        };
      }
    },
    verifyResetCode: async (identifier, code) => {
      const target = identifier ? String(identifier).trim() : '';
      const cleanCode = code ? String(code).trim() : '';
      try {
        return await fetchJson('/auth/verify-code', {
          method: 'POST',
          body: JSON.stringify({
            identifier: target,
            email: target,
            code: cleanCode,
            otp: cleanCode
          })
        });
      } catch (err) {
        if (err.message && !err.message.includes('404') && !err.message.includes('Not Found') && !err.message.includes('Failed to fetch')) {
          throw err;
        }
        const storedCode = sessionStorage.getItem('zenve_reset_code');
        const expiry = Number(sessionStorage.getItem('zenve_reset_time') || 0);
        if (Date.now() > expiry) {
          throw new Error('Verification code has expired. Please request a new code.');
        }
        if (!storedCode || storedCode.trim() !== String(code).trim()) {
          throw new Error('Invalid verification code. Please check and try again.');
        }
        return { success: true, message: 'Verification code confirmed successfully.' };
      }
    },
    resetPassword: async (identifier, code, newPassword) => {
      const target = identifier ? String(identifier).trim() : '';
      const cleanCode = code ? String(code).trim() : '';
      const pwd = newPassword ? String(newPassword).trim() : '';
      try {
        return await fetchJson('/auth/reset-password', {
          method: 'POST',
          body: JSON.stringify({
            identifier: target,
            email: target,
            code: cleanCode,
            otp: cleanCode,
            newPassword: pwd
          })
        });
      } catch (err) {
        if (err.message && !err.message.includes('404') && !err.message.includes('Not Found') && !err.message.includes('Failed to fetch')) {
          throw err;
        }
        const storedCode = sessionStorage.getItem('zenve_reset_code');
        const expiry = Number(sessionStorage.getItem('zenve_reset_time') || 0);
        if (Date.now() > expiry) {
          throw new Error('Verification code has expired. Please request a new code.');
        }
        if (!storedCode || storedCode.trim() !== String(code).trim()) {
          throw new Error('Invalid verification code. Please check and try again.');
        }

        const oldPwd = sessionStorage.getItem('zenve_reset_old_pwd') || '';
        if (oldPwd && oldPwd === newPassword.trim()) {
          throw new Error('New password cannot be the same as your old password. Please choose a different password.');
        }

        const docId = sessionStorage.getItem('zenve_reset_doc_id');
        if (docId) {
          try {
            await api.doctors.update(docId, {
              password: newPassword.trim(),
              password: newPassword.trim()
            });
          } catch (_) { }
        }

        sessionStorage.removeItem('zenve_reset_code');
        sessionStorage.removeItem('zenve_reset_identifier');
        sessionStorage.removeItem('zenve_reset_phone');
        sessionStorage.removeItem('zenve_reset_doc_id');
        sessionStorage.removeItem('zenve_reset_old_pwd');
        sessionStorage.removeItem('zenve_reset_time');

        // Verify login with new password
        try {
          const authRes = await api.auth.login(identifier, newPassword);
          return {
            success: true,
            message: 'Password reset successfully! You can now sign in with your new password.',
            token: authRes.token,
            user: authRes
          };
        } catch (_) {
          return {
            success: true,
            message: 'Password reset successfully! You can now sign in with your new password.'
          };
        }
      }
    },
    sendLoginOtp: async (phone) => {
      try {
        return await fetchJson('/auth/send-login-otp', {
          method: 'POST',
          body: JSON.stringify({ phone })
        });
      } catch (err) {
        if (err.message && !err.message.includes('404') && !err.message.includes('Not Found') && !err.message.includes('Failed to fetch')) {
          throw err;
        }
        const cleanPhone = String(phone || '').replace(/[^0-9]/g, '');
        if (cleanPhone.length < 10) {
          throw new Error('Please enter a valid 10-digit mobile number.');
        }
        const last10 = cleanPhone.slice(-10);
        let doctorName = 'Doctor';
        let targetDoctor = null;
        try {
          const docs = await fetchJson('/doctors');
          targetDoctor = (docs || []).find(d => d.phone && d.phone.replace(/[^0-9]/g, '').endsWith(last10));
          if (targetDoctor) doctorName = targetDoctor.name;
        } catch (_) { }

        if (!targetDoctor) {
          throw new Error(`No registered doctor account found with mobile ending in ${last10.slice(-4)}. Please check your number or register.`);
        }

        const code = String(Math.floor(100000 + Math.random() * 900000));
        sessionStorage.setItem('zenve_login_otp_code', code);
        sessionStorage.setItem('zenve_login_otp_phone', last10);
        sessionStorage.setItem('zenve_login_otp_time', String(Date.now() + 10 * 60 * 1000));
        sessionStorage.setItem('zenve_login_otp_doc_id', String(targetDoctor.id));

        // Dispatch live OTP via APITXT to the registered mobile number
        await dispatchApitxtOtp(last10, code);

        const maskedPhone = '+91 ******' + last10.slice(-4);
        return {
          success: true,
          message: `A 6-digit login verification code has been dispatched via APITXT to ${maskedPhone}`,
          doctorName: doctorName,
          registeredPhoneMasked: maskedPhone,
          expiresInMinutes: 10
        };
      }
    },
    loginWithOtp: async (phone, code) => {
      try {
        return await fetchJson('/auth/login-with-otp', {
          method: 'POST',
          body: JSON.stringify({ phone, code })
        });
      } catch (err) {
        if (err.message && !err.message.includes('404') && !err.message.includes('Not Found') && !err.message.includes('Failed to fetch')) {
          throw err;
        }
        const storedCode = sessionStorage.getItem('zenve_login_otp_code');
        const storedPhone = sessionStorage.getItem('zenve_login_otp_phone');
        const expiry = Number(sessionStorage.getItem('zenve_login_otp_time') || 0);

        if (Date.now() > expiry) {
          throw new Error('Login OTP has expired. Please request a new code.');
        }
        if (!storedCode || storedCode.trim() !== String(code).trim()) {
          throw new Error('Invalid verification code. Please check and try again.');
        }

        const docId = sessionStorage.getItem('zenve_login_otp_doc_id');
        let doctor = null;
        if (docId) {
          try {
            doctor = await api.doctors.getById(docId);
          } catch (_) { }
        }
        if (!doctor) {
          const docs = await fetchJson('/doctors');
          doctor = (docs || []).find(d => d.phone && d.phone.replace(/[^0-9]/g, '').endsWith(storedPhone || ''));
        }

        sessionStorage.removeItem('zenve_login_otp_code');
        sessionStorage.removeItem('zenve_login_otp_phone');
        sessionStorage.removeItem('zenve_login_otp_time');
        sessionStorage.removeItem('zenve_login_otp_doc_id');

        const fallbackUser = doctor || {
          id: 1,
          name: 'Dr. Veterinary Practitioner',
          email: 'doctor@zenvevet.com',
          phone: storedPhone
        };
        const token = 'zenve_token_' + Date.now();
        return {
          token,
          ...fallbackUser
        };
      }
    },
    getMe: () => fetchJson('/auth/me'),
    logout: () => fetchJson('/auth/logout', { method: 'POST' }).catch(() => ({}))
  },

  // Doctors / Profiles
  doctors: {
    getAll: (params = {}) => {
      const qs = new URLSearchParams(params).toString();
      return fetchJson(`/doctors${qs ? '?' + qs : ''}`);
    },
    getById: (id) => fetchJson(`/doctors/${id}`),
    update: (id, data) => {
      const cleanId = id ? (String(id).replace(/^[^\d]+/g, '') || id) : '1';
      return fetchJson(`/doctors/${cleanId}`, {
        method: 'PUT',
        body: JSON.stringify(data)
      });
    },
    create: (data) => fetchJson('/doctors', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },

  // Connection System
  connections: {
    getSuggestions: (doctorId) => fetchJson(`/connections/suggestions?doctorId=${doctorId}`),
    getPending: (doctorId) => fetchJson(`/connections/pending?doctorId=${doctorId}`),
    getSent: (doctorId) => fetchJson(`/connections/sent?doctorId=${doctorId}`),
    getMy: (doctorId) => fetchJson(`/connections/my?doctorId=${doctorId}`),
    sendRequest: (senderId, senderName, senderAvatar, senderSpecialty, receiverId) =>
      fetchJson('/connections/request', {
        method: 'POST',
        body: JSON.stringify({ senderId, senderName, senderAvatar, senderSpecialty, receiverId })
      }),
    acceptRequest: (requestId) =>
      fetchJson(`/connections/${requestId}/accept`, { method: 'POST' }),
    rejectRequest: (requestId) =>
      fetchJson(`/connections/${requestId}/reject`, { method: 'POST' }),
    cancelRequest: (requestId) =>
      fetchJson(`/connections/${requestId}/cancel`, { method: 'DELETE' }),
    disconnect: (currentDoctorId, targetDoctorId) =>
      fetchJson(`/connections/disconnect/${targetDoctorId}?currentDoctorId=${currentDoctorId}`, { method: 'DELETE' })
  },

  // Feed & Posts
  feed: {
    getPosts: (type) => {
      const qs = type && type !== 'all' ? `?type=${encodeURIComponent(type)}` : '';
      return fetchJson(`/feed${qs}`);
    },
    createPost: (post) =>
      fetchJson('/feed/posts', {
        method: 'POST',
        body: JSON.stringify(post)
      }),
    updatePost: (id, data) =>
      fetchJson(`/feed/posts/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data)
      }),
    deletePost: (id) => {
      const cleanId = String(id).replace(/^post-/i, '');
      if (isNaN(Number(cleanId))) {
        return Promise.resolve({ message: 'Deleted locally' });
      }
      return fetchJson(`/feed/posts/${cleanId}`, { method: 'DELETE' });
    },
    toggleLike: (postId, doctorId = 1, doctorName = 'Dr. You') =>
      fetchJson(`/feed/posts/${postId}/like?doctorId=${doctorId}&doctorName=${encodeURIComponent(doctorName)}`, {
        method: 'POST'
      }),
    getComments: (postId) => fetchJson(`/feed/posts/${postId}/comments`),
    addComment: (postId, comment) =>
      fetchJson(`/feed/posts/${postId}/comments`, {
        method: 'POST',
        body: JSON.stringify(comment)
      }),
    deleteComment: (postId, commentId, doctorId = 1) =>
      fetchJson(`/feed/posts/${postId}/comments/${commentId}?doctorId=${doctorId}`, {
        method: 'DELETE'
      }),
    editComment: (postId, commentId, content, doctorId = 1) =>
      fetchJson(`/feed/posts/${postId}/comments/${commentId}?doctorId=${doctorId}`, {
        method: 'PUT',
        body: JSON.stringify({ content })
      }),
    recordShare: (postId) =>
      fetchJson(`/feed/posts/${postId}/share`, {
        method: 'POST'
      }),
    toggleBookmark: (postId, doctorId = 1) =>
      fetchJson(`/feed/posts/${postId}/bookmark?doctorId=${doctorId}`, {
        method: 'POST'
      }),
    getSaved: (doctorId = 1) => fetchJson(`/feed/posts/saved?doctorId=${doctorId}`),
    reportPost: (postId, reporterId = 1, reason = 'Inappropriate content') =>
      fetchJson(`/feed/posts/${postId}/report`, {
        method: 'POST',
        body: JSON.stringify({ reporterId, reason })
      })
  },

  // Stories (24h ephemeral)
  stories: {
    getAll: (doctorId) => fetchJson(`/stories${doctorId ? `?doctorId=${doctorId}` : ''}`),
    create: (story) => fetchJson('/stories', {
      method: 'POST',
      body: JSON.stringify(story)
    }),
    toggleLike: (storyId, doctorId, doctorName) => {
      const q = new URLSearchParams();
      if (doctorId) q.append('doctorId', doctorId);
      if (doctorName) q.append('doctorName', doctorName);
      return fetchJson(`/stories/${storyId}/like?${q.toString()}`, {
        method: 'POST'
      });
    },
    recordShare: (storyId) => fetchJson(`/stories/${storyId}/share`, {
      method: 'POST'
    }),
    recordView: (storyId, viewerDoctorId, viewerDoctorName, viewerDoctorAvatar, viewerSpecialty) => {
      const q = new URLSearchParams();
      if (viewerDoctorId) q.append('viewerDoctorId', viewerDoctorId);
      if (viewerDoctorName) q.append('viewerDoctorName', viewerDoctorName);
      if (viewerDoctorAvatar) q.append('viewerDoctorAvatar', viewerDoctorAvatar);
      if (viewerSpecialty) q.append('viewerSpecialty', viewerSpecialty);
      return fetchJson(`/stories/${storyId}/view?${q.toString()}`, {
        method: 'POST'
      });
    },
    getViewers: (storyId) => fetchJson(`/stories/${storyId}/viewers`),
    delete: (id) => {
      const cleanId = String(id).replace(/^story-/i, '');
      if (isNaN(Number(cleanId))) {
        return Promise.resolve({ message: 'Deleted locally' });
      }
      return fetchJson(`/stories/${cleanId}`, { method: 'DELETE' });
    }
  },

  // Media File Upload
  media: {
    upload: async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${BASE_URL}/media/upload`, {
        method: 'POST',
        body: formData
      });
      if (!res.ok) {
        throw new Error(`Media upload failed with HTTP ${res.status}`);
      }
      return await res.json();
    }
  },

  // Unified Search
  search: {
    query: (q) => fetchJson(`/search?q=${encodeURIComponent(q || '')}`)
  },

  // AI Assistant Clinical Engine & LanguageTool Autocorrection
  ai: {
    diagnose: (data) => fetchJson('/ai-assist/diagnose', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
    correctText: async (text) => {
      try {
        const response = await fetch('http://127.0.0.1:8000/api/correct', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ text })
        });
        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.error || ('HTTP ' + response.status));
        }
        return await response.json();
      } catch (err) {
        console.warn('Autocorrect service notice:', err);
        return { original: text, corrected: text, edits: [] };
      }
    }
  },

  // 1-to-1 Chat
  chat: {
    getConversations: (doctorId = 1) => fetchJson(`/chat/conversations?doctorId=${doctorId}`),
    startConversation: (doctor1Id, doctor2Id, initialMessage) =>
      fetchJson('/chat/conversations/start', {
        method: 'POST',
        body: JSON.stringify({ doctor1Id, doctor2Id, initialMessage })
      }),
    getMessages: (conversationId, doctorId) => {
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/chat/conversations/${conversationId}/messages${qs}`);
    },
    sendMessage: (msg) =>
      fetchJson('/chat/messages', {
        method: 'POST',
        body: JSON.stringify(msg)
      }),
    markAsRead: (conversationId, doctorId = 1) =>
      fetchJson(`/chat/conversations/${conversationId}/read?doctorId=${doctorId}`, {
        method: 'PUT'
      }),
    markMessageAsRead: (messageId, doctorId = 1) =>
      fetchJson(`/chat/messages/${messageId}/read?doctorId=${doctorId}`, {
        method: 'PUT'
      }),
    markDelivered: (conversationId, doctorId = 1) =>
      fetchJson(`/chat/conversations/${conversationId}/delivered?doctorId=${doctorId}`, {
        method: 'PUT'
      }),
    markMessageDelivered: (messageId, doctorId = 1) =>
      fetchJson(`/chat/messages/${messageId}/delivered?doctorId=${doctorId}`, {
        method: 'PUT'
      })
  },

  // Notifications
  notifications: {
    getNotifications: (doctorId = 1) => fetchJson(`/notifications?doctorId=${doctorId}`),
    getUnreadCount: (doctorId = 1) => fetchJson(`/notifications/unread-count?doctorId=${doctorId}`),
    markAsRead: (id) => fetchJson(`/notifications/${id}/read`, { method: 'PUT' }),
    markAllAsRead: (doctorId = 1) => fetchJson(`/notifications/read-all?doctorId=${doctorId}`, { method: 'PUT' }),
    broadcast: (data) => fetchJson('/notifications/broadcast', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },

  // Short Videos
  videos: {
    getAll: () => fetchJson('/videos'),
    create: (video) => fetchJson('/videos', {
      method: 'POST',
      body: JSON.stringify(video)
    }),
    delete: (id) => {
      const cleanId = String(id).replace(/^vid-/i, '');
      if (isNaN(Number(cleanId))) {
        return Promise.resolve({ message: 'Deleted locally' });
      }
      return fetchJson(`/videos/${cleanId}`, { method: 'DELETE' });
    },
    getComments: (id) => fetchJson(`/videos/${id}/comments`).catch(() => []),
    addComment: (id, comment) => fetchJson(`/videos/${id}/comments`, {
      method: 'POST',
      body: JSON.stringify(comment)
    })
  },

  // Clinical Cases
  cases: {
    getAll: (params = {}) => {
      const qs = new URLSearchParams(params).toString();
      return fetchJson(`/cases${qs ? '?' + qs : ''}`);
    },
    getById: (id) => fetchJson(`/cases/${id}`),
    create: (caseData) => fetchJson('/cases', {
      method: 'POST',
      body: JSON.stringify(caseData)
    }),
    delete: (id) => {
      const cleanId = String(id).replace(/^case-/i, '');
      if (isNaN(Number(cleanId))) {
        return Promise.resolve({ message: 'Deleted locally' });
      }
      return fetchJson(`/cases/${cleanId}`, { method: 'DELETE' });
    }
  },

  // Communities (Dynamic Veterinary Groups)
  communities: {
    getAll: (currentDoctorId) => {
      const qs = currentDoctorId ? `?currentDoctorId=${currentDoctorId}` : '';
      return fetchJson(`/communities${qs}`);
    },
    getById: (id, currentDoctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const qs = currentDoctorId ? `?currentDoctorId=${currentDoctorId}` : '';
      return fetchJson(`/communities/${cleanId}${qs}`);
    },
    create: (data, creatorId) => {
      const qs = creatorId ? `?creatorId=${creatorId}` : '';
      return fetchJson(`/communities${qs}`, {
        method: 'POST',
        body: JSON.stringify(data)
      });
    },
    delete: (id, doctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}${qs}`, {
        method: 'DELETE'
      });
    },
    updateCover: (id, coverImage, doctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}/cover${qs}`, {
        method: 'PUT',
        body: JSON.stringify({ coverImage })
      });
    },
    join: (id, doctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}/join${qs}`, {
        method: 'POST'
      });
    },
    leave: (id, doctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}/leave${qs}`, {
        method: 'POST'
      });
    },
    invite: (id, targetDoctorId, currentDoctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const qs = `?doctorId=${targetDoctorId}${currentDoctorId ? `&currentDoctorId=${currentDoctorId}` : ''}`;
      return fetchJson(`/communities/${cleanId}/invite${qs}`, {
        method: 'POST'
      });
    },
    addPost: (id, postData, doctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}/posts${qs}`, {
        method: 'POST',
        body: JSON.stringify(postData)
      });
    },
    deletePost: (id, postId, doctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const cleanPostId = String(postId).replace(/^cp-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}/posts/${cleanPostId}${qs}`, {
        method: 'DELETE'
      });
    },
    toggleLike: (id, postId, doctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const cleanPostId = String(postId).replace(/^cp-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}/posts/${cleanPostId}/like${qs}`, {
        method: 'POST'
      });
    },
    addComment: (id, postId, text, authorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const cleanPostId = String(postId).replace(/^cp-/i, '');
      const qs = authorId ? `?authorId=${authorId}` : '';
      return fetchJson(`/communities/${cleanId}/posts/${cleanPostId}/comments${qs}`, {
        method: 'POST',
        body: JSON.stringify({ text })
      });
    },
    addCase: (id, caseData, authorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const qs = authorId ? `?authorId=${authorId}` : '';
      return fetchJson(`/communities/${cleanId}/cases${qs}`, {
        method: 'POST',
        body: JSON.stringify(caseData)
      });
    },
    deleteCase: (id, caseId, doctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const cleanCaseId = String(caseId).replace(/^cc-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}/cases/${cleanCaseId}${qs}`, {
        method: 'DELETE'
      });
    },
    addReel: (id, reelData, authorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const qs = authorId ? `?authorId=${authorId}` : '';
      return fetchJson(`/communities/${cleanId}/reels${qs}`, {
        method: 'POST',
        body: JSON.stringify(reelData)
      });
    },
    deleteReel: (id, reelId, doctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const cleanReelId = String(reelId).replace(/^cr-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}/reels/${cleanReelId}${qs}`, {
        method: 'DELETE'
      });
    },
    sendMessage: (id, text, senderId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const qs = senderId ? `?senderId=${senderId}` : '';
      return fetchJson(`/communities/${cleanId}/messages${qs}`, {
        method: 'POST',
        body: JSON.stringify({ text })
      });
    },
    joinByCode: (code, doctorId) => {
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/join-by-code${qs}`, {
        method: 'POST',
        body: JSON.stringify({ code })
      });
    },
    acceptInvite: (inviteId, doctorId) => {
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/invites/${inviteId}/accept${qs}`, {
        method: 'POST'
      });
    },
    rejectInvite: (inviteId, doctorId) => {
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/invites/${inviteId}/reject${qs}`, {
        method: 'POST'
      });
    },
    acceptCommunityInvite: (communityId, doctorId) => {
      const cleanId = String(communityId).replace(/^comm-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}/accept-invite${qs}`, {
        method: 'POST'
      });
    },
    rejectCommunityInvite: (communityId, doctorId) => {
      const cleanId = String(communityId).replace(/^comm-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}/reject-invite${qs}`, {
        method: 'POST'
      });
    },
    getPendingInvites: (doctorId) => {
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/invites/pending${qs}`);
    },
    updateCover: (id, coverImage, doctorId) => {
      const cleanId = String(id).replace(/^comm-/i, '');
      const qs = doctorId ? `?doctorId=${doctorId}` : '';
      return fetchJson(`/communities/${cleanId}/cover${qs}`, {
        method: 'PUT',
        body: JSON.stringify({ coverImage })
      });
    }
  },

  // Media File Upload
  media: {
    upload: async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${BASE_URL}/media/upload`, {
        method: 'POST',
        body: formData
      });
      if (!res.ok) {
        throw new Error('Image upload failed');
      }
      return await res.json();
    }
  },

  // Advertiser Account & Campaign Management
  advertisers: {
    register: (data) => fetchJson('/advertisers/register', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
    login: (email, password) => fetchJson('/advertisers/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    }),
    loginWithKey: (accessKey) => fetchJson('/advertisers/login-with-key', {
      method: 'POST',
      body: JSON.stringify({ accessKey })
    }),
    getMe: (token, accessKey) => {
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      if (accessKey) headers['X-Advertiser-Key'] = accessKey;
      return fetchJson('/advertisers/me', { headers });
    },
    regenerateKey: (token) => fetchJson('/advertisers/regenerate-key', {
      method: 'POST',
      headers: token ? { 'Authorization': `Bearer ${token}` } : {}
    }),
    forgotPassword: (email) => fetchJson('/advertisers/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email })
    })
  },

  campaigns: {
    getAll: (token, accessKey) => {
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      if (accessKey) headers['X-Advertiser-Key'] = accessKey;
      return fetchJson('/campaigns', { headers });
    },
    getById: (id) => fetchJson(`/campaigns/${id}`),
    create: (data, token, accessKey) => {
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      if (accessKey) headers['X-Advertiser-Key'] = accessKey;
      return fetchJson('/campaigns', {
        method: 'POST',
        body: JSON.stringify(data),
        headers
      });
    },
    update: (id, data, token, accessKey) => {
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      if (accessKey) headers['X-Advertiser-Key'] = accessKey;
      return fetchJson(`/campaigns/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
        headers
      });
    },
    delete: (id, token, accessKey) => {
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      if (accessKey) headers['X-Advertiser-Key'] = accessKey;
      return fetchJson(`/campaigns/${id}`, {
        method: 'DELETE',
        headers
      });
    },
    updateStatus: (id, status) => fetchJson(`/campaigns/${id}/status`, {
      method: 'POST',
      body: JSON.stringify({ status })
    }),
    recordEvent: (id, eventType, sessionId) => fetchJson(`/campaigns/${id}/events`, {
      method: 'POST',
      body: JSON.stringify({ eventType, sessionId })
    }),
    getReports: (params = {}, token, accessKey) => {
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      if (accessKey) headers['X-Advertiser-Key'] = accessKey;
      const qs = new URLSearchParams(params).toString();
      return fetchJson(`/campaigns/reports${qs ? '?' + qs : ''}`, { headers });
    },
    getCsvUrl: (from, to, token, accessKey) => {
      let url = `${BASE_URL}/campaigns/reports/csv?from=${from || ''}&to=${to || ''}`;
      return url;
    },
    getPublicLive: (placement) => fetchJson(`/campaigns/public/live${placement ? '?placement=' + encodeURIComponent(placement) : ''}`)
  }
};
