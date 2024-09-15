#!/usr/bin/env python3
"""iKoalaWala Rumble Chat Actor Rig

- LLM bot which:
    - Is hosted by OpenAI
    - Cycles through three characters on a seasonal timer
    - Welcomes newcomers
    - Can be triggered to diss mutes
- ClipRecordingCommand
- Killswitch command
- Help command

S.D.G."""

import os
from pathlib import Path
import time
import openai
import rumchat_actor

class Static:
    """Static data for this rig"""

    #Text encoding to use when opening and saving files
    text_encoding = "utf-8"

    class Rumble:
        """Data relating to Rumble"""

        #Rumble API url with key. Should be loaded from an environment variable or file. TODO
        with open("rumble_api_url.txt", encoding = Static.text_encoding) as f:
            api_url = f.read().strip()

        #User login credentials. Password should be loaded from an environment variable or file. TODO
        with open("rumble_account_credentials.txt", encoding = Static.text_encoding) as f:
            username, password = f.read().splitlines()[:2]

    class LLM:
        """Data relating to OpenAI and the LLM bot"""

        #OpenAI API key. Should be loaded from an environment variable or file. TODO
        with open("openai_api_key.txt", encoding = Static.text_encoding) as f:
            api_key = f.read().strip()

        #GPT model of choice
        gpt_model = "gpt-4o"

        #Prompts for each character the LLM will use. TODO
        character_prompts = [
            "You are the character Radshak.",
            "You are the character Meshack.",
            "You are the character Abednigo.",
            ]

        #Time a character is in action in seconds
        character_season_length = 600

        #Livestream behavior prompt
        livestream_behavior_prompt = "You are staff in a livestream chat, operating under the username {actor.username}. Keep your responses brief and polite. " + \
            f"Your messages have a {rumchat_actor.static.Message.effective_max_len} character limit." + \
                "The user will give you information on what is happening, and you should return the message you would send in response. " + \
                    "Only return the message itself."

        #User memory file location
        remembered_users_fn = os.path.join(Path(__file__).parent, "remembered_users.txt")

        #User welcome prompt
        user_welcome_prompt = "A user named {username} has entered the livestream chat. You do not remember ever seeing them before, though they may have been here sometime before you became staff. Write a short welcome, pinging them with @{username} somewhere in the message."

        #Message too long response, currently unused
        too_long_response = "That's too long. Please make it briefer."

        #User said something, respond prompt
        user_respond_prompt = "The user {message.user.username} says the following to you:\n---\n{message.text}\n---\nWrite a short response, pinging them with @{username} somewhere in the message."

    class Clip:
        """Data relating to the clip command"""

        #Default clip length
        default_len = 60

        #Max clip length
        max_len = 60 * 5

        #Folder to save clips in
        save_path = os.path.expanduser("~") + os.sep + "Videos"

        #Location to look for the OBS recording
        recording_path = os.path.expanduser("~") + os.sep + "Videos"

#Set the API key
openai.api_key = Static.LLM.api_key

class LLMChatBot:
    """LLM chat bot according to iKoalaWala's specifications"""
    def __init__(self, actor):
        """Set up our client, user memory, etc.
    actor: The RumbleChatActor object"""

        #Save the actor
        self.actor = actor

        #Create OpenAI client
        self.client = openai.OpenAI()

        #Load remembered user list, if it exists
        if os.path.exists(Static.LLM.remembered_users_fn):
            with open(Static.LLM.remembered_users_fn, encoding = Static.text_encoding) as f:
                self.remembered_users = f.read().strip().splitlines()

    def action(self, message, _):
        """Message action to be registered"""

        #Do not run the LLM on flagged messages
        if not (self.is_clean(message.user.username) and self.is_clean(message.text)):
            return

        #This is a new user, greet them
        if not self.remember_user(message.user.username):
            self.greet_user(message.user.username)
            return

        #The user pinged us, generate a response to their message
        if message.text.startswith(f"@{self.actor.username}"):
            reply = self.get_llm_message(Static.LLM.user_respond_prompt.format(message))
            if reply:
                self.actor.send_message(reply)

    def is_clean(self, expression):
        """Use OpenAI moderation to check if something is clean or not"""
        moderation_response = self.client.moderations.create(input=expression)
        flagged = moderation_response.results[0].flagged
        return not flagged

    # def auto_moderate(self, message):
    #     """Automatically moderate a message, returns True if deleted"""
    #     NotImplemented

    def remember_user(self, username):
        """Return True if we remember the user, return False and make note of them if we don't"""
        if username in self.remembered_users:
            return True

        #User was not remembered, make note
        self.remembered_users.append(username)
        with open(Static.LLM.remembered_users_fn, "a", encoding = Static.text_encoding) as f:
            f.write("\n" + username)
        return False

    def greet_user(self, username):
        """Greet a first-time chatting user"""
        Static.LLM.user_welcome_prompt.format(username = username)
        message = self.get_llm_message(Static.LLM.user_welcome_prompt.format(username = username))
        if not message: #Getting a message failed
            return
        self.actor.send_message(message)

    @property
    def current_character(self):
        """The current index of character prompts to use"""
        return (time.time() % (Static.LLM.character_season_length * len(Static.LLM.character_prompts))) // Static.LLM.character_season_length

    @property
    def current_system_prompt(self):
        """The current system LLM prompt, as defined by the current character"""
        return Static.LLM.livestream_behavior_prompt.format(actor = self.actor) + " " + Static.LLM.character_prompts[self.current_character]

    def get_llm_message(self, prompt):
        """Get an LLM response to a prompt"""
        response = self.client.chat.completions.create(
        model = Static.LLM.gpt_model,
        messages=[
            {"role": "system", "content": self.current_system_prompt},
            {"role": "user", "content": prompt},
        ]
        )
        try:
            text = response.choices[0].message.content
        except Exception as e:
            print("LLM error:", e)
            print(response)
            return

        return text

#Initialize the actor
actor = rumchat_actor.RumbleChatActor(api_url = Static.Rumble.api_url, username = Static.Rumble.username, password = Static.Rumble.password)

#Register the LLM chat bot
llmcb = LLMChatBot(actor)
actor.register_message_action(llmcb)

#Clip command
clip_command = rumchat_actor.commands.ClipRecordingCommand(
    actor = actor,
    default_duration = Static.Clip.default_len,
    max_duration = Static.Clip.max_len,
    recording_load_path = Static.Clip.recording_path,
    clip_save_path = Static.Clip.save_path,
    )
actor.register_command(clip_command)

#Killswitch command
actor.register_command(rumchat_actor.commands.KillswitchCommand(actor = actor))

#Help command
actor.register_command(rumchat_actor.commands.HelpCommand(actor = actor))

print("Starting mainloop...")
actor.mainloop()
