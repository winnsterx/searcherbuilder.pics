import Head from "next/head";
import styles from "../styles/Home.module.css";
import React, { useState, useEffect } from "react";
import axios from "axios";

export default function Home() {
  const backend = "http://127.0.0.1:5000/zeromev";

  function getEtherscanSearchers() {
    axios
      .get(backend)
      .then((resp) => {
        return Object.keys(resp.data);
      })
      .catch((err) => console.log(err));
  }

  return (
    <div className={styles.container}>
      <Head>
        <title>Searcher Database</title>
        {/* <link rel="icon" href="/favicon.ico" /> */}
      </Head>

      <main>
        <h1 className={styles.title}>
          Welcome to <a href="https://nextjs.org">Next.js!</a>
        </h1>

        <div className={styles.grid}>{getEtherscanSearchers()} </div>
      </main>
    </div>
  );
}
