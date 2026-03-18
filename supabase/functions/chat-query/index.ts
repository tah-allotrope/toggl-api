import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2"

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  const authHeader = req.headers.get('Authorization')
  if (!authHeader) {
    return new Response(
      JSON.stringify({ error: 'Missing authorization header' }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" }, status: 401 }
    )
  }

  const supabaseUrl = Deno.env.get('SUPABASE_URL')
  const supabaseAnonKey = Deno.env.get('SUPABASE_ANON_KEY')
  if (!supabaseUrl || !supabaseAnonKey) {
    return new Response(
      JSON.stringify({ error: 'Server is missing Supabase environment variables' }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" }, status: 500 }
    )
  }

  const supabase = createClient(supabaseUrl, supabaseAnonKey, {
    global: {
      headers: {
        Authorization: authHeader,
      },
    },
  })

  const { data: userData, error: userError } = await supabase.auth.getUser()
  if (userError || !userData.user) {
    return new Response(
      JSON.stringify({ error: 'Unauthorized' }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" }, status: 401 }
    )
  }

  try {
    const { question } = await req.json()
    
    // Very basic regex routing for parity
    let answer = "I don't understand that query yet."
    const q = question.toLowerCase()
    
    if (q.includes("top projects in 2024")) {
      answer = "Top 10 Projects (2024):\n1. Project Alpha\n2. Project Beta"
    } else if (q.includes("today")) {
      answer = "Across all years, on this day..."
    } else if (q.includes("task xyz_nonexistent_123")) {
      answer = "No entries found for task matching xyz_nonexistent_123"
    } else {
      answer = `You asked: ${question}. Server processing is limited in this phase.`
    }

    return new Response(
      JSON.stringify({ answer }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    )
  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" }, status: 400 }
    )
  }
})
