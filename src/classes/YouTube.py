import re
import base64
import json
import time
import os
import requests
import assemblyai as aai
import feedparser
import asyncio
import edge_tts

from utils import *
from cache import *
from llm_provider import generate_text
from config import *
from status import *
from uuid import uuid4
from constants import *
from typing import List
from moviepy.editor import *
from termcolor import colored
from selenium_firefox import *
from selenium import webdriver
from moviepy.video.fx.all import crop
from moviepy.config import change_settings
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from moviepy.video.tools.subtitles import SubtitlesClip
from webdriver_manager.firefox import GeckoDriverManager
from datetime import datetime

# Set ImageMagick Path
change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})


class YouTube:
    """
    Class for YouTube Automation.

    Steps to create a YouTube Short:
    1. Generate a topic [DONE]
    2. Generate a script [DONE]
    3. Generate metadata (Title, Description, Tags) [DONE]
    4. Generate AI Image Prompts [DONE]
    4. Generate Images based on generated Prompts [DONE]
    5. Convert Text-to-Speech [DONE]
    6. Show images each for n seconds, n: Duration of TTS / Amount of images [DONE]
    7. Combine Concatenated Images with the Text-to-Speech [DONE]
    """

    def __init__(
        self,
        account_uuid: str,
        account_nickname: str,
        fp_profile_path: str,
        niche: str,
        language: str,
    ) -> None:
        """
        Constructor for YouTube Class.

        Args:
            account_uuid (str): The unique identifier for the YouTube account.
            account_nickname (str): The nickname for the YouTube account.
            fp_profile_path (str): Path to the firefox profile that is logged into the specificed YouTube Account.
            niche (str): The niche of the provided YouTube Channel.
            language (str): The language of the Automation.

        Returns:
            None
        """
        self._account_uuid: str = account_uuid
        self._account_nickname: str = account_nickname
        self._fp_profile_path: str = fp_profile_path
        self._niche: str = niche
        self._language: str = language

        self.images = []

        # Initialize the Firefox profile
        self.options: Options = Options()

        # Set headless state of browser
        if get_headless():
            self.options.add_argument("--headless")

        if not os.path.isdir(self._fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {self._fp_profile_path}"
            )

        self.options.add_argument("-profile")
        self.options.add_argument(self._fp_profile_path)

        # Set the service
        self.service: Service = Service(GeckoDriverManager().install())

        # Initialize the browser
        self.browser: webdriver.Firefox = webdriver.Firefox(
            service=self.service, options=self.options
        )

    @property
    def niche(self) -> str:
        """
        Getter Method for the niche.

        Returns:
            niche (str): The niche
        """
        return self._niche

    @property
    def language(self) -> str:
        """
        Getter Method for the language to use.

        Returns:
            language (str): The language
        """
        return self._language

    def generate_response(self, prompt: str, model_name: str = None) -> str:
        """
        Generates an LLM Response based on a prompt and the user-provided model.

        Args:
            prompt (str): The prompt to use in the text generation.

        Returns:
            response (str): The generated AI Repsonse.
        """
        return generate_text(prompt, model_name=model_name)

    def generate_topic(self) -> str:
        """
        Generates a topic based on the YouTube Channel niche.

        Returns:
            topic (str): The generated topic.
        """
        completion = self.generate_response(
            f"Please generate a specific video idea that takes about the following topic: {self.niche}. Make it exactly one sentence. Only return the topic, nothing else."
        )

        if not completion:
            error("Failed to generate Topic.")

        self.subject = completion

        return completion

    def generate_trending_reddit_script(self) -> str:
        """
        Fetches top trending posts from Reddit (last month),
        picks the most viral one using an LLM,
        fetches the top 10 comments of that post to capture public sentiment,
        and uses the LLM to write a highly engaging Shorts script based on the event and comments.
        """

        print(colored("[+] Reddit üzerinden viral başlıklar taranıyor...", "blue"))

        subreddits = [
            "worldnews",
            "nottheonion",
            "news",
            "popculturechat",
            "WeirdNews",
            "OutOfTheLoop",
            "Damnthatsinteresting"
        ]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        posts_data = []
        post_id_map = {} # Maps an ID to its URL and title for later use
        current_id = 1

        log_file_path = os.path.join(ROOT_DIR, "scraped_reddit_news.txt")
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n--- TARAMA TARİHİ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        for sub in subreddits:
            try:
                # Top posts of the month, limit 10 per sub
                url = f"https://www.reddit.com/r/{sub}/top.json?t=month&limit=10"
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    children = data.get("data", {}).get("children", [])
                    with open(log_file_path, "a", encoding="utf-8") as f:
                        f.write(f"\nSubreddit: r/{sub}\n")
                    
                    for child in children:
                        post = child.get("data", {})
                        if post.get("stickied", False):
                            continue
                        title = post.get("title", "")
                        permalink = post.get("permalink", "")
                        ups = post.get("ups", 0)

                        if title and permalink:
                            full_url = f"https://www.reddit.com{permalink}"
                            posts_data.append(f"[{current_id}] Title: {title}")
                            post_id_map[str(current_id)] = {
                                "title": title,
                                "url": full_url
                            }
                            with open(log_file_path, "a", encoding="utf-8") as f:
                                f.write(f"  [{current_id}] ({ups} up) - {title}\n")
                            current_id += 1
            except Exception as e:
                warning(f"Failed to fetch data from r/{sub}: {e}")
                continue

        if not posts_data:
            error("Reddit could not provide any posts. Falling back to standard topic generation.")
            self.generate_topic()
            return self.generate_script()

        raw_posts_text = "\n".join(posts_data)
        print(colored(f"[+] Total {len(posts_data)} viral reddit posts found.", "cyan"))

        editor_prompt = f"""
        Here is a list of top trending Reddit posts from this month:
        {raw_posts_text}

        TASK: 
        You are an expert viral content editor for YouTube Shorts. 
        Read the list and choose the SINGLE most shocking,scandalous, or highly debated story that would make a perfect viral video.
        
        CRITICAL RULE: Return ONLY the exact ID number (e.g., 5) of the post you chose. 
        DO NOT explain your choice. DO NOT write the title. JUST THE NUMBER.
        """
        
        try:
            best_story_id_str = str(self.generate_response(editor_prompt)).strip()
            # Extract just the number in case Llama adds extra text
            match = re.search(r'\d+', best_story_id_str)
            if match:
                selected_id = match.group(0)
            else:
                selected_id = "1" # Fallback
                
            if selected_id not in post_id_map:
                 selected_id = list(post_id_map.keys())[0]

        except Exception as e:
             warning(f"Editor selection failed: {e}. Falling back to the first post.")
             selected_id = list(post_id_map.keys())[0]

        selected_post = post_id_map[selected_id]
        selected_title = selected_post["title"]
        selected_url = selected_post["url"]

        if get_verbose():
            print(colored(f"[+] Editor's Selection (ID {selected_id}):\n{selected_title}", "green"))
        
        print(colored("[+] Fetching the top 10 most upvoted comments for the selected post...", "cyan"))

        # Fetch top 10 comments for the selected post
        comments_data = []
        try:
            # Append .json to the permalink to get post data + comments
            comment_url = f"{selected_url}.json"
            response = requests.get(comment_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # data[1] contains the comments tree
                comments_list = data[1].get("data", {}).get("children", [])
                
                # Extract top 10 top-level comments
                count = 0
                for comment in comments_list:
                    if count >= 10:
                        break
                    
                    kind = comment.get("kind")
                    if kind == "t1": # t1 means it's a comment
                        body = comment.get("data", {}).get("body", "")
                        ups = comment.get("data", {}).get("ups", 0)
                        
                        # Filter out deleted/removed comments
                        if body and body not in ["[deleted]", "[removed]"]:
                            # Clean up newlines for cleaner prompt
                            clean_body = body.replace('\n', ' ').strip()
                            comments_data.append(f"- (Upvotes: {ups}) {clean_body}")
                            count += 1
                            
        except Exception as e:
            warning(f"Yorumlar çekilirken hata oluştu: {e}")

        raw_comments_text = "\n".join(comments_data) if comments_data else "No comments available."

        print(colored("[+] Gemini (Script Writer) writing the script...", "cyan"))

        # STORYTELLER LLAMA (Writing the script with public sentiment)
        sentence_length = get_script_sentence_length()
        writer_prompt = f"""
        STORY / EVENT: {selected_title}
        
        TOP 10 PUBLIC COMMENTS (The Sentiment):
        {raw_comments_text}

        TASK:
        Write a {sentence_length}-sentence YouTube Shorts script based on this event.
        
        CRITICAL NARRATIVE RULES:
        1. YOU MUST INCORPORATE THE PUBLIC SENTIMENT: Use the top comments provided to understand how people feel about this event (e.g., are they angry, mocking, supportive, shocked?). 
        2. WEAVE THE SENTIMENT INTO THE SCRIPT: Describe the event, but also mention the public backlash, theories, or jokes. (e.g., "People are absolutely losing their minds over this, with some saying...")
        3. SAFETY WARNING (CRITICAL): You are writing for YouTube. DO NOT directly quote or copy any profanity, slurs, or highly toxic language from the comments. Understand the *emotion* of the comment and rewrite it cleanly. (e.g., change "This guy is a f***ing idiot" to "The internet is mercilessly dragging him for this decision").

        FORMATTING & PACING RULES:
        1. Script must be exactly {sentence_length} sentences long.
        2. Start immediately with a massive hook translated naturally to {self.language}. (e.g., "Did you hear about..." or "The internet is divided over...").
        3. Write the script entirely in {self.language}.
        4. Keep your language easy to understand.
        5. End with an open-ended question or cliffhanger that encourages viewers to comment based on the sentiment you presented.
        
        STRICT OUTPUT RULES:
        DO NOT write anything else other than the script. 
        NO markdown, NO titles, NO voiceover tags (like [Narrator]). 
        DO NOT ADD ANY INTRODUCTIONS before going into the script. 
        JUST RETURN THE RAW SPOKEN SCRIPT.
        """
        
        completion = self.generate_response(writer_prompt)
        completion = re.sub(r"\*", "", completion)

        if not completion:
            error("Senaryo üretilemedi, normal konuya dönülüyor.")
            return self.generate_script()

        self.script = completion
        
        # Video visual subject extraction for metadata and image generation
        self.subject = self.generate_response(f"What is the core visual subject of this script in 4-6 words? Script: {self.script}. Return only the words.")

        if get_verbose():
            success(f"Generated Viral Script (with Public Sentiment):\n{self.script}")

        return completion

    def generate_trending_news_script(self) -> str:
        """
        Fetches news from multiple RSS feeds (Weird News & Gossip), 
        uses LLM to pick the absolute most viral one,
        and then uses LLM again to write a hook-heavy Shorts script.
        """

        print(colored("[+] Tuhaf Haberler ve Magazin kaynakları taranıyor...", "blue"))

        rss_feeds = [
            "https://www.tmz.com/rss.xml", # Hollywood Magazin
            "https://www.eonline.com/syndication/feeds/rssfeeds/topstories.xml", # Ünlü Dedikoduları
            "https://www.mirror.co.uk/news/weird-news/?service=rss", # Mirror Tuhaf Haberler
            "https://feeds.skynews.com/feeds/rss/strange.xml" # Sky News İlginç/Tuhaf Haberler
        ]

        news_items = []
        news_id = 1
        
        for feed_url in rss_feeds:
            try:
                feed = feedparser.parse(feed_url)
                entry_count = 10
                if(feed.entries.__len__() < 10):
                    entry_count = feed.entries.__len__()
                for entry in feed.entries[:entry_count]:
                    news_items.append(f"[{news_id}] Headline: {entry.title} - Summary: {entry.get('summary', '')}")
                    news_id += 1
            except Exception as e:
                continue
        
        raw_news_data = "\n".join(news_items)

        print(colored(f"[+] Toplam {len(news_items)} güncel haber toplandı. Llama 3 (Editör) en viral olanı seçiyor...", "cyan"))

        # EDITOR LLAMA (Selecting the most viral story)
        editor_prompt = f"""
        Here is a list of today's weird news and gossip:
        {raw_news_data}

        TASK: 
        You are an expert viral content editor. Read the list and choose the SINGLE most shocking, weird, or scandalous story that would make a perfect viral YouTube Short.
        Selected story should have a strong hook and narratable or has to be a newsworthy event that can be turned into a narratable story. Or about a known celebrity with a good story.
        Return ONLY the Headline and Summary of the story you chose. The summary and the event should be narratable.
        DO NOT explain your choice. DO NOT add any extra text. DO NOT start with here is your summary etc. JUST RETURN THE RAW HEADLINE AND DETAILED SUMMARY OF THE MOST VIRAL STORY.
        """
        
        best_story = self.generate_response(editor_prompt)
        
        if get_verbose():
            print(colored(f"[+] Editörün Seçimi:\n{best_story}", "green"))
        print(colored("[+] Llama 3 (Senarist) bu haberi viral bir Shorts senaryosuna çeviriyor...", "cyan"))

        # STORYTELLER LLAMA (Writing the script with a hook)
        sentence_length = get_script_sentence_length()
        writer_prompt = f"""
        Story: {best_story}

        TASK:
        Write a {sentence_length}-sentence YouTube Shorts script based on this content/story.
        Script must be {sentence_length}-sentences long.
        DO NOT write anything else other than the script. DO NOT add any titles, headings, or voiceover tags, DO NOT ADD ANY INTRODUCTIONS before going into the script. JUST RETURN THE RAW SCRIPT.
        RULES:
        1. If the video content is about a weird shocking new etc. start with a massive hook like "Did you hear about..." or "You won't believe what just happened..." (Translate the hook naturally to {self.language}).
        2. If the video content is about a celebrity gossip, start with a hook like "Guess what <celebrity_name> just did..." or "You won't believe what <celebrity_name> is up to..." (Translate the hook naturally to {self.language}).
        3. Keep the tone highly engaging, fast-paced, mysterious, and like you are telling a juicy secret. You can use Hooks-Development-Cliffhanger structure if it fits the story. The script should be written in a way that maximizes viewer retention.
        4. Write the script entirely in {self.language}.
        5. Use short sentences and end with a cliffhanger to maximize viewer retention.
        6. Strictly avoid dry, encyclopedic, or wiki-style factual recitations.
        7. Keep your language easy to understand for non-native speakers, avoid complex words and jargon.
        8. DO NOT use sensitive words that trigger AI safety filters. Avoid them or change them with synonyms.
        9. You can give an open edge to viewers to write comments like "What would you do this in this situation?" or "Do you think it is acceptable for a diplomate to do this?" etc. Just do this naturally if it fits the story, don't force it.
        10. CRITICAL RULE: No markdown, no titles, no voiceover tags. JUST RETURN THE RAW SPOKEN SCRIPT.
        11. CRITICAL RULE: DO NOT write "Here is the script" OR ANY INDUCTORY TEXT. Start IMMEDIATELY with the first word of the script. DO NOT output any conversational filler.
        12. ONLY RETURN THE RAW CONTENT OF THE SCRIPT. DO NOT INCLUDE "VOICEOVER", "NARRATOR" OR SIMILAR INDICATORS OF WHAT SHOULD BE SPOKEN AT THE BEGINNING OF EACH PARAGRAPH OR LINE. YOU MUST NOT MENTION THE PROMPT, OR ANYTHING ABOUT THE SCRIPT ITSELF. ALSO, NEVER TALK ABOUT THE AMOUNT OF PARAGRAPHS OR LINES. JUST WRITE THE SCRIPT. DO NOT START WITH ANY INTRODUCTION SENTENCE.
        """
        
        completion = self.generate_response(writer_prompt)
        completion = re.sub(r"\*", "", completion)

        if not completion:
            error("Senaryo üretilemedi, normal konuya dönülüyor.")
            return self.generate_script()

        self.script = completion
        
        # Video visual subject extraction for metadata and image generation
        self.subject = self.generate_response(f"What is the core visual subject of this script in 4-6 words? Script: {self.script}. Return only the words.")

        if get_verbose():
            success(f"Generated Viral Script:\n{self.script}")

        return completion

    def generate_script(self) -> str:
        """
        Generate a script for a video, depending on the subject of the video, the number of paragraphs, and the AI model.

        Returns:
            script (str): The script of the video.
        """
        sentence_length = get_script_sentence_length()
        prompt = f"""
        Generate a script for a video in {sentence_length} sentences, depending on the subject of the video.

        The script is to be returned as a string with the specified number of paragraphs.

        Here is an example of a string:
        "This is an example string."

        Do not under any circumstance reference this prompt in your response.

        Get straight to the point, don't start with unnecessary things like, "welcome to this video".

        There are some guidelines you should follow:
        1)Core Narrative Style (Edutainment & Mystery): Strictly avoid dry, encyclopedic, or wiki-style factual recitations. Adopt the persona of a mysterious, captivating storyteller revealing hidden truths. Use short, punchy sentences and emotionally charged adjectives (e.g., terrifying, forgotten, forbidden, chilling).

        2)Factual Flexibility for Engagement: Your primary goal is 100% viewer retention and entertainment, not 100% strict historical accuracy. You have explicit permission to slightly bend historical truths, lean into urban legends, or present compelling conspiracy theories as dramatic possibilities. Make the mundane sound deeply conspiratorial or mysterious.

        3)The "No-Intro" Rule: NEVER start the script with generic introductions like "Today we will talk about...", "Did you know...", or "Welcome to...". Dive straight into the narrative.

        4)Strict 3-Act Structure:
            1. The Hook (First 1-2 sentences): Start immediately with a shocking claim, an unsettling visual description, or a mind-bending question that challenges what the viewer thinks they know.
            2. The Development (Core narrative): Tell the story like a gripping thriller. Frame the events around secret agendas, hidden motives, or inexplicable phenomena. Connect the dots in a way that builds continuous tension.
            3. The Climax & Cliffhanger (Last 1-2 sentences): Do not resolve the story neatly. End with a profound, lingering question or a plot twist that leaves the audience questioning reality and eager to comment.

        Pacing & Delivery: Write the script specifically for a deep, charismatic voiceover. Use ellipses (...) and paragraph breaks to indicate dramatic pauses. The script should read like a dramatic monologue from a suspense thriller.

        Obviously, the script should be related to the subject of the video.
        
        YOU MUST NOT EXCEED THE {sentence_length} SENTENCES LIMIT. MAKE SURE THE {sentence_length} SENTENCES ARE SHORT.
        YOU MUST NOT INCLUDE ANY TYPE OF MARKDOWN OR FORMATTING IN THE SCRIPT, NEVER USE A TITLE.
        YOU MUST WRITE THE SCRIPT IN THE LANGUAGE SPECIFIED IN [LANGUAGE].
        ONLY RETURN THE RAW CONTENT OF THE SCRIPT. DO NOT INCLUDE "VOICEOVER", "NARRATOR" OR SIMILAR INDICATORS OF WHAT SHOULD BE SPOKEN AT THE BEGINNING OF EACH PARAGRAPH OR LINE. YOU MUST NOT MENTION THE PROMPT, OR ANYTHING ABOUT THE SCRIPT ITSELF. ALSO, NEVER TALK ABOUT THE AMOUNT OF PARAGRAPHS OR LINES. JUST WRITE THE SCRIPT
        
        Subject: {self.subject}
        Language: {self.language}
        """
        completion = self.generate_response(prompt)

        # Apply regex to remove *
        completion = re.sub(r"\*", "", completion)

        if not completion:
            error("The generated script is empty.")
            return

        if len(completion) > 5000:
            if get_verbose():
                warning("Generated Script is too long. Retrying...")
            return self.generate_script()

        self.script = completion

        return completion

    def generate_metadata(self) -> dict:
        """
        Generates Video metadata for the to-be-uploaded YouTube Short (Title, Description).

        Returns:
            metadata (dict): The generated metadata.
        """
        title = self.generate_response(
            f"Please generate a YouTube Video Title for the following subject, including hashtags: {self.subject}. Only return the title, nothing else. Limit the title under 100 characters."
        )

        if len(title) > 100:
            if get_verbose():
                warning("Generated Title is too long. Retrying...")
            return self.generate_metadata()

        description = self.generate_response(
            f"Please generate a YouTube Video Description for the following script: {self.script}. Only return the description, nothing else."
        )

        self.metadata = {"title": title, "description": description}

        return self.metadata
    
    def analyze_script_mood(self) -> str:
        """
        Llama 3'ü kullanarak senaryonun duygu durumunu analiz eder 
        ve ona uygun bir müzik klasörü adı döndürür.
        """
        info(" => Senaryo duygu analizi yapılıyor (Müzik seçimi için)...")
        
        prompt = f"""
        Analyze the following video script and determine its core mood or theme.
        
        You MUST choose ONLY ONE number from the list below that best matches the script.
        
        1 = Mystery, secrets, hidden facts
        2 = Success, pride, overcoming obstacles
        3 = Sadness, emotional struggles, tragedy
        4 = Disaster, catastrophe, shocking bad news
        5 = Happiness, wholesome, good news
        6 = Sorrow, grief, heartbreaking
        
        Script:
        {self.script}
        
        STRICT RULES:
        Return ONLY a single digit number (1, 2, 3, 4, 5, or 6).
        NO text. NO explanations. NO markdown. Just the number.
        """
        
        try:
            completion = str(self.generate_response(prompt))
            import re
            match = re.search(r'[1-6]', completion)
            
            if match:
                choice = int(match.group(0))
            else:
                choice = 1 

            mood_map = {
                1: "Mystery",
                2: "Success_Honour",
                3: "Sadness",
                4: "Disaster",
                5: "Happiness",
                6: "Sorrow"
            }
            
            selected_mood = mood_map.get(choice, "Success_Honour")
            info(f" => Llama Duygu Seçimi: {choice} -> Klasör: {selected_mood}")
            
            return selected_mood
            
        except Exception as e:
            warning(f"Duygu analizi başarısız oldu: {e}. Varsayılan klasör seçiliyor.")
            return "Success_Honour" 
        
    def generate_prompts(self) -> List[str]:
        """ 
        Generates AI Image Prompts based on the provided Video Script.
        Uses advanced prompt engineering for Image-to-Image (I2I) continuity using the <1> tag.

        Returns:
            image_prompts (List[str]): Generated List of image prompts.
        """
        
        prompt = f"""
        Act as an expert storyboard artist and cinematic director.
        Your task is to break down the following video script into a chronological sequence of image prompts for an AI Image Generator.

        Subject: {self.subject}

        CORE RULES FOR CONSISTENCY AND STORYTELLING:
        1. DYNAMIC FRAME COUNT: Use exactly as many frames as needed to tell the story visually from beginning to end. If a quick action needs 3 frames, use 3. If a complex story needs 12, use 12.
        
        2. CHRONOLOGICAL PROGRESSION: Each prompt must represent a new, distinct beat in the story. Do not repeat the same action just with different colors. The images must flow logically.
        
        3. THE REFERENCE TAG (<1>) FOR VISUAL CONTINUITY (CRITICAL RULE): 
           You have access to an Image-to-Image memory system. 
           - IF a frame takes place in the EXACT SAME SCENE with the SAME CHARACTERS as the IMMEDIATELY PRECEDING frame, you MUST add the tag <1> at the very end of the prompt.
           - WHEN USING <1>: You can just refer to the previous image. (e.g., "The same man from the reference image is now running <1>").
           - NEVER use the <1> tag on the very first frame, as there is no previous image to reference.
           
        4. SCENE CHANGES (NO TAG):
           - IF the scene changes to a NEW LOCATION, a NEW TIME, or introduces COMPLETELY NEW SUBJECTS, DO NOT use the <1> tag.
           - When there is NO tag, you MUST provide a highly detailed, full description of the new environment and characters from scratch.
           
        5. CINEMATIC DETAIL & SAFETY: Use engaging, cinematic adjectives (e.g., "dramatic lighting", "wide angle", "hyper-realistic"). DO NOT use sensitive words (e.g., avoid blood, kill, shoot, naked, gore). Use safe synonyms.

        OUTPUT FORMAT:
        You must return a raw JSON-Array of strings. 
        YOU MUST ONLY RETURN THE JSON-ARRAY OF STRINGS. NO intro text, NO markdown formatting, NO comments.

        YOUR OUTPUT MUST BE IN THE FOLLOWING EXAMPLE FORMAT:
        EXAMPLE FORMAT AND LOGIC:
        [
            "A tall muscular man wearing a torn blue denim jacket walking down a rainy, neon-lit cyberpunk alleyway. Cinematic lighting, 8k resolution",
            "The same man from the reference image looking over his shoulder in panic as a shadow approaches him in the alleyway <1>",
            "The man in the reference image sprinting away fast, motion blur <1>",
            "A completely new scene: Inside a brightly lit, futuristic police station where a detective is looking at a computer screen. Wide angle, hyper-detailed"
        ]

        For context, here is the full video script:
        {self.script}
        """

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
        )

        image_prompts = []

        start_idx = completion.find('[')
        end_idx = completion.rfind(']')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = completion[start_idx:end_idx + 1]
            try:
                import json
                image_prompts = json.loads(json_str)
            except Exception as e:
                if get_verbose():
                    warning(f"LLM JSON formatını bozdu: {e}. Tekrar deneniyor...")
                return self.generate_prompts()
        else:
            if get_verbose():
                warning("LLM cevabında liste [...] bulunamadı. Tekrar deneniyor...")
                print(completion)
            return self.generate_prompts()

        if not isinstance(image_prompts, list) or len(image_prompts) == 0:
            if get_verbose():
                warning("Geçerli bir liste oluşturulamadı. Tekrar deneniyor...")
            return self.generate_prompts()

        self.image_prompts = image_prompts

        success(f"Generated {len(image_prompts)} highly consistent Image Prompts with I2I Tagging.")

        return image_prompts

    def _persist_image(self, image_bytes: bytes, provider_label: str) -> str:
        """
        Writes generated image bytes to a PNG file in .mp.

        Args:
            image_bytes (bytes): Image payload
            provider_label (str): Label for logging

        Returns:
            path (str): Absolute image path
        """
        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")

        with open(image_path, "wb") as image_file:
            image_file.write(image_bytes)

        if get_verbose():
            info(f' => Wrote image from {provider_label} to "{image_path}"')

        self.images.append(image_path)
        return image_path

    def generate_image_nanobanana2(self, prompt: str, reference_image: str = None) -> str:
        """
        Generates an AI Image using Nano Banana 2 API (Gemini image API), optionally using a reference image.
        """
        if get_verbose():
            ref_status = "WITH reference" if reference_image else "NO reference"
            info(f"Generating Image using Nano Banana 2 API ({ref_status}): {prompt}")
        else:
            print(f"Generating Image using Nano Banana 2 API: {prompt}")

        time.sleep(5)
        api_key = get_nanobanana2_api_key()
        if not api_key:
            error("nanobanana2_api_key is not configured.")
            return None

        base_url = get_nanobanana2_api_base_url().rstrip("/")
        model = get_nanobanana2_model()
        aspect_ratio = get_nanobanana2_aspect_ratio()

        endpoint = f"{base_url}/models/{model}:generateContent"
        
        # Temel Payload
        parts = [{"text": prompt}]

        # Referans görsel varsa ve yolda mevcutsa ekle
        if reference_image and os.path.exists(reference_image):
            try:
                import mimetypes
                with open(reference_image, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                
                mime_type, _ = mimetypes.guess_type(reference_image)
                if not mime_type:
                    mime_type = "image/png"

                parts.append({
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": img_data
                    }
                })
            except Exception as e:
                warning(f"Referans görsel eklenemedi, sadece metin ile devam ediliyor: {e}")

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": aspect_ratio},
            },
        }

        try:
            response = requests.post(
                endpoint,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=300,
            )
            response.raise_for_status()
            body = response.json()

            candidates = body.get("candidates", [])
            for candidate in candidates:
                content = candidate.get("content", {})
                for part in content.get("parts", []):
                    inline_data = part.get("inlineData") or part.get("inline_data")
                    if not inline_data:
                        continue
                    data = inline_data.get("data")
                    mime_type = inline_data.get("mimeType") or inline_data.get("mime_type", "")
                    if data and str(mime_type).startswith("image/"):
                        image_bytes = base64.b64decode(data)
                        return self._persist_image(image_bytes, "Nano Banana 2 API")

            if get_verbose():
                warning(f"Nano Banana 2 did not return an image payload. Response: {body}")
            return None
        except Exception as e:
            if get_verbose():
                warning(f"Failed to generate image with Nano Banana 2 API: {str(e)}")
            return None

    def generate_image(self, prompt: str, reference_image: str = None) -> str:
        """
        Generates an AI Image based on the given prompt using Nano Banana 2.

        Args:
            prompt (str): Reference for image generation
            referance_image: if using an image input in the image prompt.

        Returns:
            path (str): The path to the generated image.
        """
        return self.generate_image_nanobanana2(prompt, reference_image)

    # def generate_script_to_speech(self, tts_instance: TTS) -> str:
    #     """
    #     Converts the generated script into Speech using KittenTTS and returns the path to the wav file.

    #     Args:
    #         tts_instance (tts): Instance of TTS Class.

    #     Returns:
    #         path_to_wav (str): Path to generated audio (WAV Format).
    #     """
    #     path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".wav")

    #     # Clean script, remove every character that is not a word character, a space, a period, a question mark, or an exclamation mark.
    #     self.script = re.sub(r"[^\w\s.?!]", "", self.script)

    #     tts_instance.synthesize(self.script, path)

    #     self.tts_path = path

    #     if get_verbose():
    #         info(f' => Wrote TTS to "{path}"')

    #     return path

    def generate_script_to_speech(self) -> str:
        """
        Converts the generated script into Speech using Microsoft Edge-TTS (Bulut Sesleri).
        """
        path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp3") 

        self.script = re.sub(r"[^\w\s.?!]", "", self.script)

        voice = get_tts_voice() or "en-US-ChristopherNeural"

        if get_verbose():
            info(f" => Generating quality audio with Edge-TTS using voice: {voice}")

        communicate = edge_tts.Communicate(self.script, voice)
        asyncio.run(communicate.save(path))

        self.tts_path = path

        if get_verbose():
            info(f' => Wrote quality TTS to "{path}"')

        return path
    
    def add_video(self, video: dict) -> None:
        """
        Adds a video to the cache.

        Args:
            video (dict): The video to add

        Returns:
            None
        """
        videos = self.get_videos()
        videos.append(video)

        cache = get_youtube_cache_path()

        with open(cache, "r") as file:
            previous_json = json.loads(file.read())

            # Find our account
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    account["videos"].append(video)

            # Commit changes
            with open(cache, "w") as f:
                f.write(json.dumps(previous_json))

    def generate_subtitles(self, audio_path: str) -> str:
        """
        Generates subtitles for the audio using the configured STT provider.

        Args:
            audio_path (str): The path to the audio file.

        Returns:
            path (str): The path to the generated SRT File.
        """
        provider = str(get_stt_provider() or "local_whisper").lower()

        if provider == "local_whisper":
            return self.generate_subtitles_local_whisper(audio_path)

        if provider == "third_party_assemblyai":
            return self.generate_subtitles_assemblyai(audio_path)

        warning(f"Unknown stt_provider '{provider}'. Falling back to local_whisper.")
        return self.generate_subtitles_local_whisper(audio_path)

    def generate_subtitles_assemblyai(self, audio_path: str) -> str:
        """
        Generates subtitles using AssemblyAI.

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        aai.settings.api_key = get_assemblyai_api_key()
        config = aai.TranscriptionConfig(speech_models=["universal-2"])
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_path)
        subtitles = transcript.export_subtitles_srt()

        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")

        with open(srt_path, "w") as file:
            file.write(subtitles)

        return srt_path

    def _format_srt_timestamp(self, seconds: float) -> str:
        """
        Formats a timestamp in seconds to SRT format.

        Args:
            seconds (float): Seconds

        Returns:
            ts (str): HH:MM:SS,mmm
        """
        total_millis = max(0, int(round(seconds * 1000)))
        hours = total_millis // 3600000
        minutes = (total_millis % 3600000) // 60000
        secs = (total_millis % 60000) // 1000
        millis = total_millis % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def generate_subtitles_local_whisper(self, audio_path: str) -> str:
        """
        Generates subtitles using local Whisper (faster-whisper).

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            error(
                "Local STT selected but 'faster-whisper' is not installed. "
                "Install it or switch stt_provider to third_party_assemblyai."
            )
            raise

        model = WhisperModel(
            get_whisper_model(),
            device=get_whisper_device(),
            compute_type=get_whisper_compute_type(),
        )
        segments, _ = model.transcribe(audio_path, vad_filter=True)

        lines = []
        for idx, segment in enumerate(segments, start=1):
            start = self._format_srt_timestamp(segment.start)
            end = self._format_srt_timestamp(segment.end)
            text = str(segment.text).strip()

            if not text:
                continue

            lines.append(str(idx))
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        subtitles = "\n".join(lines)
        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write(subtitles)

        return srt_path

    def combine(self, mood_category: str = "Success_Honour") -> str:
        """
        Combines everything into the final video.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        combined_image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp4")
        threads = get_threads()
        tts_clip = AudioFileClip(self.tts_path)
        max_duration = tts_clip.duration
        req_dur = max_duration / len(self.images)

        # Make a generator that returns a TextClip when called with consecutive
        generator = lambda txt: TextClip(
            txt,
            font=os.path.join(get_fonts_dir(), "Inter-Black.ttf"), 
            fontsize=100,       
            color="white",         
            stroke_color="black", 
            stroke_width=2, 
            interline=5,     
            size=(1080, 1920),  
            method="caption",   
        )

        print(colored("[+] Combining images...", "blue"))

        clips = []
        tot_dur = 0
        # Add downloaded clips over and over until the duration of the audio (max_duration) has been reached
        while tot_dur < max_duration:
            for image_path in self.images:
                clip = ImageClip(image_path)
                clip.duration = req_dur
                clip = clip.set_fps(30)

                # Not all images are same size,
                # so we need to resize them
                if round((clip.w / clip.h), 4) < 0.5625:
                    if get_verbose():
                        info(f" => Resizing Image: {image_path} to 1080x1920")
                    clip = crop(
                        clip,
                        width=clip.w,
                        height=round(clip.w / 0.5625),
                        x_center=clip.w / 2,
                        y_center=clip.h / 2,
                    )
                else:
                    if get_verbose():
                        info(f" => Resizing Image: {image_path} to 1920x1080")
                    clip = crop(
                        clip,
                        width=round(0.5625 * clip.h),
                        height=clip.h,
                        x_center=clip.w / 2,
                        y_center=clip.h / 2,
                    )
                clip = clip.resize((1080, 1920))

                # FX (Fade In)
                # clip = clip.fadein(2)

                clips.append(clip)
                tot_dur += clip.duration

        final_clip = concatenate_videoclips(clips)
        final_clip = final_clip.set_fps(30)
        random_song = choose_random_song(category=mood_category)

        subtitles = None
        try:
            subtitles_path = self.generate_subtitles(self.tts_path)
            equalize_subtitles(subtitles_path, 40)
            subtitles = SubtitlesClip(subtitles_path, generator)
            subtitles.set_pos(("center", "center"))
        except Exception as e:
            warning(f"Failed to generate subtitles, continuing without subtitles: {e}")

        random_song_clip = AudioFileClip(random_song).set_fps(44100)

        # Turn down volume
        random_song_clip = random_song_clip.fx(afx.volumex, 0.1)
        comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), random_song_clip])

        final_clip = final_clip.set_audio(comp_audio)
        final_clip = final_clip.set_duration(tts_clip.duration)

        if subtitles is not None:
            final_clip = CompositeVideoClip([final_clip, subtitles])

        final_clip.write_videofile(combined_image_path, threads=threads)

        success(f'Wrote Video to "{combined_image_path}"')

        return combined_image_path

    def generate_video(self, method: str = "niche") -> str:
        """
        Generates a YouTube Short based on the selected method.

        Args:
            tts_instance (TTS): Instance of TTS Class.
            method (str): "niche" for standard topic generation, "trends" for trending news.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        # Seçilen metoda göre konu ve senaryo üret
        if method == "news_trends":
            self.generate_trending_news_script()
        elif method == "reddit_trends":
            self.generate_trending_reddit_script()
        else:
            self.generate_topic()
            self.generate_script()

        # Generate the Metadata
        self.generate_metadata()

        # Generate the Image Prompts
        self.generate_prompts()

        # Generate the Images
        previous_image_path = None
        
        for prompt in self.image_prompts:
            use_reference = False
            clean_prompt = prompt
            
            # LLM "<1>" tag check
            if "<1>" in prompt:
                use_reference = True
                clean_prompt = prompt.replace("<1>", "").strip()
                
                if get_verbose():
                    info(" -> Continuity detected (<1>), getting previous image as ref.")

            # image gen
            if use_reference and previous_image_path:
                current_image_path = self.generate_image(clean_prompt, reference_image=previous_image_path)
            else:
                current_image_path = self.generate_image(clean_prompt, reference_image=None)

            # store on success
            if current_image_path:
                previous_image_path = current_image_path

        # Generate the TTS
        self.generate_script_to_speech()

        #Mood detect for song selection.
        script_mood = self.analyze_script_mood()

        # Combine everything (Bulduğumuz duyguyu combine'a gönderiyoruz)
        path = self.combine(mood_category=script_mood)

        if get_verbose():
            info(f" => Generated Video: {path}")

        self.video_path = os.path.abspath(path)

        return path
    
    def get_channel_id(self) -> str:
        """
        Gets the Channel ID of the YouTube Account.

        Returns:
            channel_id (str): The Channel ID.
        """
        driver = self.browser
        driver.get("https://studio.youtube.com")
        time.sleep(2)
        channel_id = driver.current_url.split("/")[-1]
        self.channel_id = channel_id

        return channel_id

    def upload_video(self) -> bool:
        """
        Uploads the video to YouTube.

        Returns:
            success (bool): Whether the upload was successful or not.
        """
        try:
            self.get_channel_id()

            driver = self.browser
            verbose = get_verbose()

            # Go to youtube.com/upload
            driver.get("https://www.youtube.com/upload")

            # Set video file
            FILE_PICKER_TAG = "ytcp-uploads-file-picker"
            file_picker = driver.find_element(By.TAG_NAME, FILE_PICKER_TAG)
            INPUT_TAG = "input"
            file_input = file_picker.find_element(By.TAG_NAME, INPUT_TAG)
            file_input.send_keys(self.video_path)

            # Wait for upload to finish
            time.sleep(5)

            # Set title
            textboxes = driver.find_elements(By.ID, YOUTUBE_TEXTBOX_ID)

            title_el = textboxes[0]
            description_el = textboxes[-1]

            if verbose:
                info("\t=> Setting title...")

            title_el.click()
            time.sleep(1)
            title_el.clear()
            title_el.send_keys(self.metadata["title"])

            if verbose:
                info("\t=> Setting description...")

            # Set description
            time.sleep(10)
            description_el.click()
            time.sleep(0.5)
            description_el.clear()
            description_el.send_keys(self.metadata["description"])

            time.sleep(0.5)

            # Set `made for kids` option
            if verbose:
                info("\t=> Setting `made for kids` option...")

            is_for_kids_checkbox = driver.find_element(
                By.NAME, YOUTUBE_MADE_FOR_KIDS_NAME
            )
            is_not_for_kids_checkbox = driver.find_element(
                By.NAME, YOUTUBE_NOT_MADE_FOR_KIDS_NAME
            )

            if not get_is_for_kids():
                is_not_for_kids_checkbox.click()
            else:
                is_for_kids_checkbox.click()

            time.sleep(0.5)

            # Click next
            if verbose:
                info("\t=> Clicking next...")

            next_button = driver.find_element(By.ID, YOUTUBE_NEXT_BUTTON_ID)
            next_button.click()

            # Click next again
            if verbose:
                info("\t=> Clicking next again...")
            next_button = driver.find_element(By.ID, YOUTUBE_NEXT_BUTTON_ID)
            next_button.click()

            # Wait for 2 seconds
            time.sleep(2)

            # Click next again
            if verbose:
                info("\t=> Clicking next again...")
            next_button = driver.find_element(By.ID, YOUTUBE_NEXT_BUTTON_ID)
            next_button.click()

            # Set as unlisted
            if verbose:
                info("\t=> Setting as unlisted...")

            radio_button = driver.find_elements(By.XPATH, YOUTUBE_RADIO_BUTTON_XPATH)
            radio_button[2].click()

            if verbose:
                info("\t=> Clicking done button...")

            # Click done button
            done_button = driver.find_element(By.ID, YOUTUBE_DONE_BUTTON_ID)
            done_button.click()

            # Wait for 2 seconds
            time.sleep(2)

            # Get latest video
            if verbose:
                info("\t=> Getting video URL...")

            # Get the latest uploaded video URL
            driver.get(
                f"https://studio.youtube.com/channel/{self.channel_id}/videos/short"
            )
            time.sleep(2)
            videos = driver.find_elements(By.TAG_NAME, "ytcp-video-row")
            first_video = videos[0]
            anchor_tag = first_video.find_element(By.TAG_NAME, "a")
            href = anchor_tag.get_attribute("href")
            if verbose:
                info(f"\t=> Extracting video ID from URL: {href}")
            video_id = href.split("/")[-2]

            # Build URL
            url = build_url(video_id)

            self.uploaded_video_url = url

            if verbose:
                success(f" => Uploaded Video: {url}")

            # Add video to cache
            self.add_video(
                {
                    "title": self.metadata["title"],
                    "description": self.metadata["description"],
                    "url": url,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

            # Close the browser
            driver.quit()

            return True
        except:
            self.browser.quit()
            return False

    def get_videos(self) -> List[dict]:
        """
        Gets the uploaded videos from the YouTube Channel.

        Returns:
            videos (List[dict]): The uploaded videos.
        """
        if not os.path.exists(get_youtube_cache_path()):
            # Create the cache file
            with open(get_youtube_cache_path(), "w") as file:
                json.dump({"videos": []}, file, indent=4)
            return []

        videos = []
        # Read the cache file
        with open(get_youtube_cache_path(), "r") as file:
            previous_json = json.loads(file.read())
            # Find our account
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    videos = account["videos"]

        return videos
