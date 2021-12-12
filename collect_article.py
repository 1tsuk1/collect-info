import itertools
import json
import os
import textwrap
import urllib.parse
from typing import List

import feedparser
import requests
from omegaconf import OmegaConf

POST_TEXT_URL = "https://slack.com/api/conversations.history"
TOKEN = os.environ["SLACK_TOKEN"]


class SearchArticleRSS(object):
    def __init__(self, *args):
        pass

    @classmethod
    def search_all_tag_site_rss(cls, tags):
        all_tag_site_rss = [SearchArticleRSS._search_all_site_rss(tag) for tag in tags]
        flatten_all_tag_site_rss = itertools.chain.from_iterable(
            all_tag_site_rss
        )  #  二次元から一次元に変換
        return flatten_all_tag_site_rss

    @classmethod
    def _search_all_site_rss(cls, tag):
        encode_tag = urllib.parse.quote(tag)
        qiita_rss = feedparser.parse("https://qiita.com/tags/" + encode_tag + "/feed")
        zenn_rss = feedparser.parse("https://zenn.dev/topics/" + encode_tag + "/feed")
        hatena_rss = feedparser.parse(
            "https://b.hatena.ne.jp/search/tag?q=" + encode_tag + "&mode=rss&users=1"
        )
        all_site_rsses = [[qiita_rss, tag], [hatena_rss, tag], [zenn_rss, tag]]

        return all_site_rsses


class SendArticleToSlack(object):
    def __init__(self, config):

        self.username = config["username"]

        self.slack_channel_ids = config["slack_channel_ids"]
        self.slack_url_dict = config["slack_url_dict"]
        # self.slack_url_dict = config["slack_url_dict"][0]

        self.not_want_to_send_links = config["not_want_to_send_links"]

    def _search_post_link(self) -> List[str]:
        """
        各チャンネルでの各投稿メッセージ内で「リンク: 」に続くURLをリストで取得する関数

        Returns:
            List[str]: 各投稿メッセージ内のURL
        """
        all_post_link_lists = []
        # 各チャンネルの投稿メッセージを取得
        for slack_channel_id in self.slack_channel_ids:
            payload = {"channel": slack_channel_id, "token": TOKEN, "limit": 1000}
            response = requests.get(POST_TEXT_URL, params=payload)
            json_data = response.json()
            msgs = json_data["messages"]
            post_link_lists = self._extract_post_link(msgs)
            all_post_link_lists.append(post_link_lists)

        return all_post_link_lists

    def _extract_post_link(self, msgs):
        """以前の投稿のリンクをリストで取得"""
        post_link_lists = []
        for msg in msgs:
            split_text = msg["text"].split("\n")
            if "リンク:" in split_text:
                link_idx = split_text.index("リンク:") + 1
                append_link = split_text[link_idx]
                append_link = append_link.replace(
                    "amp;", ""
                )  # 「&」が含まれていると，amp;が追加されてしまうため削除
                post_link_lists.append(append_link)
        return post_link_lists

    def _judge_should_send_article(self, entry, previous_post_link_lists):
        is_not_previous_send_link = f"<{entry.link}>" not in previous_post_link_lists
        is_not_want_to_send_links = not any(
            [
                not_want_to_send_link in entry.link
                for not_want_to_send_link in self.not_want_to_send_links
            ]
        )

        should_send_article = is_not_previous_send_link and is_not_want_to_send_links

        return should_send_article

    @classmethod
    def _create_send_text(self, title: str, link: str):
        text = textwrap.dedent(
            """
                *━━━━━━━━━━━━━━━━━━━━*
                *タイトル*:
                {title}
                ---------------------------
                リンク:
                {link}
                *━━━━━━━━━━━━━━━━━━━━*
        """.format(
                title=title, link=link
            )
        ).strip()

        return text

    def _send_text(self, send_articles: List):

        for entry, tag in send_articles:
            send_text = SendArticleToSlack._create_send_text(entry.title, entry.link)
            data = json.dumps(
                {
                    "username": self.username,
                    "icon_emoji": tag,
                    "text": send_text,
                    "unfurl_links": True,
                }
            )
            print(self.slack_url_dict)
            print(tag)

            requests.post(self.slack_url_dict[tag], data=data)

    def send_article(self, all_article_rsses):

        # step1:以前投稿したリンクを取得
        previous_post_link_lists = self._search_post_link()

        # step2:投稿する記事を選定
        send_articles = [
            [entry, tag]
            for rsses, tag in all_article_rsses
            for entry in rsses.entries
            if self._judge_should_send_article(entry, previous_post_link_lists)
        ]

        # step3: 投稿
        self._send_text(send_articles)


if __name__ == "__main__":

    # 設定した情報を取得
    config_path = "config.yaml"
    config = OmegaConf.load(config_path)
    tags = config["tags"]

    # 記事の取得
    all_article_rsses = SearchArticleRSS.search_all_tag_site_rss(tags)

    # slackへ投稿
    send_to_slack = SendArticleToSlack(config)
    send_to_slack.send_article(all_article_rsses)

